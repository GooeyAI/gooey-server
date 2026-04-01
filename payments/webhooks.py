from copy import copy
from decimal import Decimal
import uuid

import sentry_sdk
import stripe
from django.db import transaction
from loguru import logger

from app_users.models import PaymentProvider, TransactionReason
from daras_ai_v2 import paypal, settings
from gooeysite.bg_db_conn import db_middleware
from workspaces.models import Workspace
from .models import SeatType, Subscription, SubscriptionSeat
from .plans import PricingPlan
from .tasks import (
    send_monthly_spending_notification_email,
    send_payment_failed_email_with_invoice,
)


class PaypalWebhookHandler:
    PROVIDER = PaymentProvider.PAYPAL

    @classmethod
    def handle_sale_completed(cls, sale: paypal.Sale):
        if not sale.billing_agreement_id:
            logger.info(f"sale {sale} is not a subscription sale... skipping")
            return

        pp_sub = paypal.Subscription.retrieve(sale.billing_agreement_id)
        assert pp_sub.custom_id, (
            f"PayPal subscription {pp_sub.id} is missing workspace_id/uid"
        )
        assert pp_sub.plan_id, f"PayPal subscription {pp_sub.id} is missing plan ID"

        plan = PricingPlan.get_by_paypal_plan_id(pp_sub.plan_id)
        assert plan, f"Plan {pp_sub.plan_id} not found"

        charged_dollars = int(float(sale.amount.total))  # convert to dollars
        if charged_dollars != plan.monthly_charge:
            # log so that we can investigate, and record the payment as usual
            logger.critical(
                f"paypal: charged amount ${charged_dollars} does not match plan's monthly charge ${plan.monthly_charge}"
            )

        add_balance_for_payment(
            workspace=Workspace.objects.from_pp_custom_id(pp_sub.custom_id),
            amount=plan.credits,
            invoice_id=sale.id,
            payment_provider=cls.PROVIDER,
            charged_amount=charged_dollars * 100,
            reason=TransactionReason.SUBSCRIBE,
            plan=plan.db_value,
        )

    @classmethod
    def handle_subscription_updated(cls, pp_sub: paypal.Subscription):
        logger.info(f"Paypal subscription updated {pp_sub.id}")

        assert pp_sub.custom_id, (
            f"PayPal subscription {pp_sub.id} is missing workspace_id/uid"
        )
        assert pp_sub.plan_id, f"PayPal subscription {pp_sub.id} is missing plan ID"

        plan = PricingPlan.get_by_paypal_plan_id(pp_sub.plan_id)
        assert plan, f"Plan with id={pp_sub.plan_id} not found"

        if pp_sub.status.lower() != "active":
            logger.info(
                "Subscription is not active. Ignoring event", subscription=pp_sub
            )
            return

        set_workspace_subscription(
            provider=cls.PROVIDER,
            plan=plan,
            workspace=Workspace.objects.from_pp_custom_id(pp_sub.custom_id),
            external_id=pp_sub.id,
        )

    @classmethod
    def handle_subscription_cancelled(cls, pp_sub: paypal.Subscription):
        assert pp_sub.custom_id, f"PayPal subscription {pp_sub.id} is missing uid"
        set_workspace_subscription(
            workspace=Workspace.objects.from_pp_custom_id(pp_sub.custom_id),
            plan=PricingPlan.STARTER,
            provider=None,
            external_id=None,
        )


class StripeWebhookHandler:
    PROVIDER = PaymentProvider.STRIPE

    @classmethod
    def handle_invoice_paid(cls, workspace: Workspace, invoice: stripe.Invoice):
        from app_users.tasks import save_stripe_default_payment_method

        kwargs = {}
        if invoice.subscription and invoice.subscription_details:
            try:
                kwargs["plan"] = PricingPlan.get_by_key(
                    invoice.subscription_details.metadata.get(
                        settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD
                    )
                ).db_value
            except KeyError as e:
                sentry_sdk.capture_exception(e)
            match invoice.billing_reason:
                case "subscription_create":
                    reason = TransactionReason.SUBSCRIPTION_CREATE
                case "subscription_cycle":
                    reason = TransactionReason.SUBSCRIPTION_CYCLE
                case "subscription_update":
                    reason = TransactionReason.SUBSCRIPTION_UPDATE
                case _:
                    reason = TransactionReason.SUBSCRIBE
        elif invoice.metadata and invoice.metadata.get("auto_recharge"):
            reason = TransactionReason.AUTO_RECHARGE
        else:
            reason = TransactionReason.ADDON

        if (
            PricingPlan.from_sub(workspace.subscription) == PricingPlan.TEAM
            and invoice.subscription
        ):
            amount = 0
            charged_amount = round(Decimal(invoice.amount_paid))
        else:
            amount = invoice.lines.data[0].quantity
            charged_amount = invoice.lines.data[0].amount

        add_balance_for_payment(
            workspace=workspace,
            amount=amount,
            invoice_id=invoice.id,
            payment_provider=cls.PROVIDER,
            charged_amount=charged_amount,
            reason=reason,
            **kwargs,
        )

        if reason == TransactionReason.SUBSCRIPTION_CYCLE:
            # reset for all members:
            workspace.reset_member_balance(invoice_id=invoice.id)
        elif reason in [
            TransactionReason.SUBSCRIPTION_UPDATE,
            TransactionReason.SUBSCRIPTION_CREATE,
        ]:
            set_subscription_seats_from_stripe_sub(
                workspace.subscription,
                stripe_sub=stripe.Subscription.retrieve(
                    invoice.subscription, expand=["items"]
                ),
                invoice_id=invoice.id,
            )

        save_stripe_default_payment_method.delay(
            payment_intent_id=invoice.payment_intent,
            workspace_id=workspace.id,
            reason=reason,
        )

    @classmethod
    def handle_checkout_session_completed(cls, session_data):
        setup_intent_id = session_data.get("setup_intent")
        if not setup_intent_id:
            # not a setup mode checkout -- do nothing
            return

        setup_intent = stripe.SetupIntent.retrieve(setup_intent_id)
        if sub_id := setup_intent.metadata.get("subscription_id"):
            # subscription_id was passed to metadata when creating the session
            stripe.Subscription.modify(
                sub_id, default_payment_method=setup_intent.payment_method
            )
        elif customer_id := session_data.get("customer"):
            # no subscription_id, so update the customer's default payment method instead
            stripe.Customer.modify(
                customer_id,
                invoice_settings=dict(
                    default_payment_method=setup_intent.payment_method
                ),
            )

    @classmethod
    def handle_subscription_updated(
        cls, workspace: Workspace, stripe_sub: stripe.Subscription
    ):
        logger.info(f"Stripe subscription updated: {stripe_sub.id}")

        try:
            plan = PricingPlan.get_by_key(
                stripe_sub.metadata[settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD]
            )
        except KeyError:
            product = stripe.Product.retrieve(
                stripe_sub.plan.product, expand=["default_price"]
            )
            plan = PricingPlan.get_by_stripe_product(product)
            assert plan is not None, f"Plan for product {product.id} not found"

        if stripe_sub.status.lower() != "active":
            logger.info(
                "Subscription is not active. Ignoring event", subscription=stripe_sub
            )
            return

        quantity = 0
        charged_amount = 0

        for item in stripe_sub["items"].data:
            quantity += item.quantity
            charged_amount += item.price.unit_amount * item.quantity

        db_sub = set_workspace_subscription(
            provider=cls.PROVIDER,
            plan=plan,
            workspace=workspace,
            external_id=stripe_sub.id,
            amount=quantity,
            charged_amount=charged_amount,
        )
        set_subscription_seats_from_stripe_sub(
            db_sub,
            stripe_sub=stripe_sub,
            invoice_id=f"{stripe_sub.id}:update_{uuid.uuid4()}",
        )

    @classmethod
    def handle_subscription_cancelled(cls, workspace: Workspace):
        db_sub = set_workspace_subscription(
            provider=cls.PROVIDER,
            plan=PricingPlan.STARTER,
            workspace=workspace,
            external_id=None,
        )
        set_subscription_seats_from_stripe_sub(
            db_sub, stripe_sub=None, invoice_id=str(uuid.uuid4())
        )

    @classmethod
    def handle_invoice_failed(cls, workspace: Workspace, data: dict):
        if stripe.Charge.list(payment_intent=data["payment_intent"], limit=1).has_more:
            # we must have already sent an invoice for this to the user. so we should just ignore this event
            logger.info("Charge already exists for this payment intent")
            return

        if data.get("metadata", {}).get("auto_recharge"):
            send_payment_failed_email_with_invoice.delay(
                workspace_id=workspace.id,
                invoice_url=data["hosted_invoice_url"],
                dollar_amt=data["amount_due"] / 100,
                subject="Payment failure on your Gooey.AI auto-recharge",
            )
        elif data.get("subscription_details", {}):
            send_payment_failed_email_with_invoice.delay(
                workspace_id=workspace.id,
                invoice_url=data["hosted_invoice_url"],
                dollar_amt=data["amount_due"] / 100,
                subject="Payment failure on your Gooey.AI subscription",
            )


@transaction.atomic
def add_balance_for_payment(
    *,
    workspace: Workspace,
    amount: int,
    invoice_id: str,
    payment_provider: PaymentProvider,
    charged_amount: int,
    **kwargs,
):
    workspace.add_balance_raw(
        amount=amount,
        invoice_id=invoice_id,
        charged_amount=charged_amount,
        payment_provider=payment_provider,
        **kwargs,
    )

    if not workspace.is_paying:
        workspace.is_paying = True
        workspace.save(update_fields=["is_paying"])

    if (
        workspace.subscription
        and workspace.subscription.should_send_monthly_spending_notification()
    ):
        send_monthly_spending_notification_email.delay(workspace_id=workspace.id)


def set_workspace_subscription(
    *,
    workspace: Workspace,
    plan: PricingPlan,
    provider: PaymentProvider | None,
    external_id: str | None,
    amount: int = 0,
    charged_amount: int = 0,
    cancel_old: bool = True,
) -> Subscription:
    with transaction.atomic():
        old_sub = workspace.subscription
        if old_sub:
            new_sub = copy(old_sub)
        else:
            old_sub = None
            new_sub = Subscription()

        new_sub.plan = plan.db_value
        new_sub.amount = amount
        new_sub.charged_amount = charged_amount
        new_sub.payment_provider = provider
        new_sub.external_id = external_id
        new_sub.full_clean()
        new_sub.save()

        if not old_sub:
            workspace.subscription = new_sub
            workspace.save(update_fields=["subscription"])

    # cancel previous subscription if it's not the same as the new one
    if cancel_old and old_sub and old_sub.external_id != external_id:
        old_sub.billed_seats().all().delete()
        old_sub.cancel()

    return new_sub


def get_seat_counts_from_stripe_sub(
    stripe_sub: stripe.Subscription,
) -> dict[str, int]:
    seat_counts: dict[str, int] = {}
    for item in stripe_sub["items"].data:
        if isinstance(item.price.product, str):
            product = stripe.Product.retrieve(item.price.product)
        else:
            product = item.price.product
        if key := product.metadata.get(settings.STRIPE_ITEM_SEAT_TYPE_METADATA_FIELD):
            seat_counts[key] = item.quantity
        else:
            logger.warning(
                f"Stripe subscription item {item.id} is missing seat type metadata. Skipping seat count for this item."
            )
    return seat_counts


@db_middleware
@transaction.atomic
def set_subscription_seats_from_stripe_sub(
    db_sub: Subscription,
    stripe_sub: stripe.Subscription | None,
    invoice_id: str,
):
    plan = PricingPlan.from_sub(db_sub)
    if plan not in [PricingPlan.TEAM] or not stripe_sub:
        # if the plan doesn't have seats, delete all existing seats
        db_sub.seats.all().delete()
        return

    seat_types_by_key = {st.key: st for st in SeatType.objects.filter(is_public=True)}
    new_seat_counts = get_seat_counts_from_stripe_sub(stripe_sub)
    current_seats = (
        db_sub.billed_seats().select_related("seat_type").order_by("-assigned_to").all()
    )

    for seat in current_seats:
        if count := new_seat_counts.pop(seat.seat_type.key, 0):
            # same as current seat
            new_seat_counts[seat.seat_type.key] = count - 1
        elif new_seat_counts:
            # reassign this seat to the new seat type
            key, count = new_seat_counts.popitem()
            count -= 1
            if count > 0:
                new_seat_counts[key] = count

            old_limit = seat.seat_type.monthly_credit_limit
            seat.seat_type = seat_types_by_key[key]
            seat.save(update_fields=["seat_type"])

            if seat.assigned_to_id:
                new_limit = seat.seat_type.monthly_credit_limit
                if seat.assigned_to.balance <= old_limit <= new_limit:
                    # seat type has been upgraded or has same credit limit
                    # `balance <= old limit` checks that we are in a valid state
                    to_add = new_limit - old_limit
                else:
                    # seat type has been downgraded
                    # or user's balance was in invalid state (> old limit)
                    # balance + (new_limit - balance) = new_limit
                    to_add = new_limit - seat.assigned_to.balance

                seat.assigned_to.add_balance(
                    amount=to_add,
                    invoice_id=f"{invoice_id}/{seat.id}",
                    reason=TransactionReason.MEMBER_SEAT_CHANGE,
                    plan=db_sub.plan,
                )
        else:
            seat.delete()

    seats_to_create = []
    for seat_type_key, new_count in new_seat_counts.items():
        seats_to_create += [
            SubscriptionSeat(
                subscription=db_sub, seat_type=seat_types_by_key[seat_type_key]
            )
            for _ in range(new_count)
        ]
    SubscriptionSeat.objects.bulk_create(seats_to_create)

    auto_assign_team_seats(db_sub.workspace, invoice_id=invoice_id)


def auto_assign_team_seats(
    workspace: Workspace, invoice_id: str, member_ids: list[str] | None = None
):
    memberships_qs = (
        workspace.memberships.select_related("user")
        .select_for_update()
        .filter(deleted__isnull=True)
        .order_by("-created_at")
    )
    if member_ids is not None:
        memberships_qs = memberships_qs.filter(id__in=member_ids)

    memberships = {m.id: m for m in memberships_qs}
    workspace_seats = (
        workspace.subscription.billed_seats()
        .select_related("seat_type")
        .select_for_update()
        .order_by("-seat_type__monthly_credit_limit")
        .all()
    )

    members_with_seat = set(
        seat.assigned_to_id
        for seat in workspace_seats
        if seat.assigned_to_id is not None
    )
    members_without_seat = [
        m for m_id, m in memberships.items() if m_id not in members_with_seat
    ]
    unassigned_seats = [seat for seat in workspace_seats if seat.assigned_to_id is None]

    if not unassigned_seats and not members_without_seat:
        return

    ret = {}
    for seat, member in zip(unassigned_seats, members_without_seat):
        seat.assigned_to = member
        seat.save(update_fields=["assigned_to"])
        member.add_balance(
            amount=seat.seat_type.monthly_credit_limit - member.balance,
            invoice_id=f"{invoice_id}/{seat.id}",
            reason=TransactionReason.MEMBER_SEAT_CHANGE,
            plan=workspace.subscription.plan,
        )
        ret[member.pk] = seat

    return ret
