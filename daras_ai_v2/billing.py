from typing import Literal

import gooey_gui as gui
import stripe
from django.core.exceptions import ValidationError

from app_users.models import AppUser, PaymentProvider
from daras_ai_v2 import icons, settings, paypal
from daras_ai_v2.fastapi_tricks import get_app_route_url
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.settings import templates
from daras_ai_v2.user_date_widgets import render_local_date_attrs
from payments.models import PaymentMethodSummary
from payments.plans import PricingPlan
from scripts.migrate_existing_subscriptions import available_subscriptions

rounded_border = "w-100 border shadow-sm rounded py-4 px-3"


PlanActionLabel = Literal["Upgrade", "Downgrade", "Contact Us", "Your Plan"]


def billing_page(user: AppUser):
    render_payments_setup()

    if user.subscription and user.subscription.plan != PricingPlan.STARTER.db_value:
        render_current_plan(user)

    with gui.div(className="my-5"):
        render_credit_balance(user)

    with gui.div(className="my-5"):
        selected_payment_provider = render_all_plans(user)

    with gui.div(className="my-5"):
        render_addon_section(user, selected_payment_provider)

    if user.subscription:
        if user.subscription.payment_provider == PaymentProvider.STRIPE:
            with gui.div(className="my-5"):
                render_auto_recharge_section(user)
        with gui.div(className="my-5"):
            render_payment_information(user)

    with gui.div(className="my-5"):
        render_billing_history(user)


def render_payments_setup():
    from routers.account import payment_processing_route

    gui.html(
        templates.get_template("payment_setup.html").render(
            settings=settings,
            payment_processing_url=get_app_route_url(payment_processing_route),
        )
    )


def render_current_plan(user: AppUser):
    plan = PricingPlan.from_sub(user.subscription)
    provider = (
        PaymentProvider(user.subscription.payment_provider)
        if user.subscription.payment_provider
        else None
    )

    with gui.div(className=f"{rounded_border} border-dark"):
        # ROW 1: Plan title and next invoice date
        left, right = left_and_right()
        with left:
            gui.write(f"#### Gooey.AI {plan.title}")

            if provider:
                gui.write(
                    f"[{icons.edit} Manage Subscription](#payment-information)",
                    unsafe_allow_html=True,
                )
        with right, gui.div(className="d-flex align-items-center gap-1"):
            if provider and (
                next_invoice_ts := gui.run_in_thread(
                    user.subscription.get_next_invoice_timestamp, cache=True
                )
            ):
                gui.html("Next invoice on ")
                gui.pill(
                    "...",
                    text_bg="dark",
                    **render_local_date_attrs(
                        next_invoice_ts,
                        date_options={"day": "numeric", "month": "long"},
                    ),
                )

        if plan is PricingPlan.ENTERPRISE:
            # charge details are not relevant for Enterprise customers
            return

        # ROW 2: Plan pricing details
        left, right = left_and_right(className="mt-5")
        with left:
            gui.write(f"# {plan.pricing_title()}", className="no-margin")
            if plan.monthly_charge:
                provider_text = f" **via {provider.label}**" if provider else ""
                gui.caption("per month" + provider_text)

        with right, gui.div(className="text-end"):
            gui.write(f"# {plan.credits:,} credits", className="no-margin")
            if plan.monthly_charge:
                gui.write(
                    f"**${plan.monthly_charge:,}** monthly renewal for {plan.credits:,} credits"
                )


def render_credit_balance(user: AppUser):
    gui.write(f"## Credit Balance: {user.balance:,}")
    gui.caption(
        "Every time you submit a workflow or make an API call, we deduct credits from your account."
    )


def render_all_plans(user: AppUser) -> PaymentProvider:
    current_plan = (
        PricingPlan.from_sub(user.subscription)
        if user.subscription
        else PricingPlan.STARTER
    )
    all_plans = [plan for plan in PricingPlan if not plan.deprecated]

    gui.write("## All Plans")
    plans_div = gui.div(className="mb-1")

    if user.subscription and user.subscription.payment_provider:
        selected_payment_provider = user.subscription.payment_provider
    else:
        with gui.div():
            selected_payment_provider = PaymentProvider[
                payment_provider_radio() or PaymentProvider.STRIPE.name
            ]

    def _render_plan(plan: PricingPlan):
        if plan == current_plan:
            extra_class = "border-dark"
        else:
            extra_class = "bg-light"
        with gui.div(className="d-flex flex-column h-100"):
            with gui.div(
                className=f"{rounded_border} flex-grow-1 d-flex flex-column p-3 mb-2 {extra_class}"
            ):
                _render_plan_details(plan)
                _render_plan_action_button(
                    user=user,
                    plan=plan,
                    current_plan=current_plan,
                    payment_provider=selected_payment_provider,
                )

    with plans_div:
        grid_layout(4, all_plans, _render_plan, separator=False)

    with gui.div(className="my-2 d-flex justify-content-center"):
        gui.caption(
            f"**[See all features & benefits]({settings.PRICING_DETAILS_URL})**"
        )

    return selected_payment_provider


def _render_plan_details(plan: PricingPlan):
    with gui.div(className="flex-grow-1"):
        with gui.div(className="mb-4"):
            with gui.tag("h4", className="mb-0"):
                gui.html(plan.title)
            gui.caption(
                plan.description,
                style={
                    "minHeight": "calc(var(--bs-body-line-height) * 2em)",
                    "display": "block",
                },
            )
        with gui.div(className="my-3 w-100"):
            with gui.tag("h4", className="my-0 d-inline me-2"):
                gui.html(plan.pricing_title())
            with gui.tag("span", className="text-muted my-0"):
                gui.html(plan.pricing_caption())
        gui.write(plan.long_description, unsafe_allow_html=True)


def _render_plan_action_button(
    user: AppUser,
    plan: PricingPlan,
    current_plan: PricingPlan,
    payment_provider: PaymentProvider | None,
):
    btn_classes = "w-100 mt-3"
    if plan == current_plan:
        gui.button("Your Plan", className=btn_classes, disabled=True, type="tertiary")
    elif plan.contact_us_link:
        with gui.link(
            to=plan.contact_us_link,
            className=btn_classes + " btn btn-theme btn-primary",
        ):
            gui.html("Contact Us")
    elif (
        user.subscription and user.subscription.plan == PricingPlan.ENTERPRISE.db_value
    ):
        # don't show upgrade/downgrade buttons for enterprise customers
        # assumption: anyone without a payment provider attached is admin/enterprise
        return
    else:
        if plan.credits > current_plan.credits:
            label, btn_type = ("Upgrade", "primary")
        else:
            label, btn_type = ("Downgrade", "secondary")

        if user.subscription and user.subscription.external_id:
            # subscription exists, show upgrade/downgrade button
            _render_update_subscription_button(
                label,
                user=user,
                current_plan=current_plan,
                plan=plan,
                className=f"{btn_classes} btn btn-theme btn-{btn_type}",
            )
        else:
            assert payment_provider is not None  # for sanity
            _render_create_subscription_button(
                label,
                btn_type=btn_type,
                user=user,
                plan=plan,
                payment_provider=payment_provider,
            )


def _render_create_subscription_button(
    label: PlanActionLabel,
    *,
    btn_type: str,
    user: AppUser,
    plan: PricingPlan,
    payment_provider: PaymentProvider,
):
    match payment_provider:
        case PaymentProvider.STRIPE:
            key = f"stripe-sub-{plan.key}"
            render_stripe_subscription_button(
                user=user,
                label=label,
                plan=plan,
                btn_type=btn_type,
                key=key,
            )
        case PaymentProvider.PAYPAL:
            render_paypal_subscription_button(plan=plan)


def _render_update_subscription_button(
    label: PlanActionLabel,
    *,
    user: AppUser,
    current_plan: PricingPlan,
    plan: PricingPlan,
    className: str = "",
):
    key = f"change-sub-{plan.key}"
    match label:
        case "Downgrade":
            downgrade_modal = gui.Modal(
                "Confirm downgrade",
                key=f"downgrade-plan-modal-{plan.key}",
            )
            if gui.button(
                label,
                className=className,
                key=key,
            ):
                downgrade_modal.open()

            if downgrade_modal.is_open():
                with downgrade_modal.container():
                    gui.write(
                        f"""
    Are you sure you want to change from:  
    **{current_plan.title} ({fmt_price(current_plan)})** to **{plan.title} ({fmt_price(plan)})**?
                     """,
                        className="d-block py-4",
                    )
                    with gui.div(className="d-flex w-100"):
                        if gui.button(
                            "Downgrade",
                            className="btn btn-theme bg-danger border-danger text-white",
                            key=f"{key}-confirm",
                        ):
                            change_subscription(user, plan)
                        if gui.button(
                            "Cancel",
                            className="border border-danger text-danger",
                            key=f"{key}-cancel",
                        ):
                            downgrade_modal.close()
        case _:
            if gui.button(label, className=className, key=key):
                change_subscription(
                    user,
                    plan,
                    # when upgrading, charge the full new amount today: https://docs.stripe.com/billing/subscriptions/billing-cycle#reset-the-billing-cycle-to-the-current-time
                    billing_cycle_anchor="now",
                )


def fmt_price(plan: PricingPlan) -> str:
    if plan.monthly_charge:
        return f"${plan.monthly_charge:,}/month"
    else:
        return "Free"


def change_subscription(user: AppUser, new_plan: PricingPlan, **kwargs):
    from routers.account import account_route
    from routers.account import payment_processing_route

    current_plan = PricingPlan.from_sub(user.subscription)

    if new_plan == current_plan:
        raise gui.RedirectException(get_app_route_url(account_route), status_code=303)

    if new_plan == PricingPlan.STARTER:
        user.subscription.cancel()
        raise gui.RedirectException(
            get_app_route_url(payment_processing_route), status_code=303
        )

    match user.subscription.payment_provider:
        case PaymentProvider.STRIPE:
            if not new_plan.supports_stripe():
                gui.error(f"Stripe subscription not available for {new_plan}")

            subscription = stripe.Subscription.retrieve(user.subscription.external_id)
            stripe.Subscription.modify(
                subscription.id,
                items=[
                    {"id": subscription["items"].data[0], "deleted": True},
                    new_plan.get_stripe_line_item(),
                ],
                metadata={
                    settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD: new_plan.key,
                },
                **kwargs,
                proration_behavior="none",
            )
            raise gui.RedirectException(
                get_app_route_url(payment_processing_route), status_code=303
            )

        case PaymentProvider.PAYPAL:
            if not new_plan.supports_paypal():
                gui.error(f"Paypal subscription not available for {new_plan}")

            subscription = paypal.Subscription.retrieve(user.subscription.external_id)
            paypal_plan_info = new_plan.get_paypal_plan()
            approval_url = subscription.update_plan(
                plan_id=paypal_plan_info["plan_id"],
                plan=paypal_plan_info["plan"],
            )
            raise gui.RedirectException(approval_url, status_code=303)

        case _:
            gui.error("Not implemented for this payment provider")


def payment_provider_radio(**props) -> str | None:
    with gui.div(className="d-flex"):
        gui.write("###### Pay Via", className="d-block me-3")
        return gui.radio(
            "",
            options=PaymentProvider.names,
            format_func=lambda name: f'<span class="me-3">{PaymentProvider[name].label}</span>',
            **props,
        )


def render_addon_section(user: AppUser, selected_payment_provider: PaymentProvider):
    if user.subscription:
        gui.write("# Purchase More Credits")
    else:
        gui.write("# Purchase Credits")
    gui.caption(f"Buy more credits. $1 per {settings.ADDON_CREDITS_PER_DOLLAR} credits")

    if user.subscription and user.subscription.payment_provider:
        provider = PaymentProvider(user.subscription.payment_provider)
    else:
        provider = selected_payment_provider
    match provider:
        case PaymentProvider.STRIPE:
            render_stripe_addon_buttons(user)
        case PaymentProvider.PAYPAL:
            render_paypal_addon_buttons()


def render_paypal_addon_buttons():
    selected_amt = gui.horizontal_radio(
        "",
        settings.ADDON_AMOUNT_CHOICES,
        format_func=lambda amt: f"${amt:,}",
        checked_by_default=False,
    )
    if selected_amt:
        gui.js(
            f"setPaypalAddonQuantity({int(selected_amt) * settings.ADDON_CREDITS_PER_DOLLAR})"
        )
    gui.div(
        id="paypal-addon-buttons",
        className="mt-2",
        style={"width": "fit-content"},
    )
    gui.div(id="paypal-result-message")


def render_stripe_addon_buttons(user: AppUser):
    for dollat_amt in settings.ADDON_AMOUNT_CHOICES:
        render_stripe_addon_button(dollat_amt, user)


def render_stripe_addon_button(dollat_amt: int, user: AppUser):
    confirm_purchase_modal = gui.Modal(
        "Confirm Purchase", key=f"confirm-purchase-{dollat_amt}"
    )
    if gui.button(f"${dollat_amt:,}", type="primary"):
        if user.subscription and user.subscription.payment_provider:
            confirm_purchase_modal.open()
        else:
            stripe_addon_checkout_redirect(user, dollat_amt)

    if not confirm_purchase_modal.is_open():
        return
    with confirm_purchase_modal.container():
        gui.write(
            f"""
                Please confirm your purchase:  
                 **{dollat_amt * settings.ADDON_CREDITS_PER_DOLLAR:,} credits for ${dollat_amt}**.
                 """,
            className="py-4 d-block text-center",
        )
        with gui.div(className="d-flex w-100 justify-content-end"):
            if gui.session_state.get("--confirm-purchase"):
                success = gui.run_in_thread(
                    user.subscription.stripe_attempt_addon_purchase,
                    args=[dollat_amt],
                    placeholder="Processing payment...",
                )
                if success is None:
                    return
                gui.session_state.pop("--confirm-purchase")
                if success:
                    confirm_purchase_modal.close()
                else:
                    gui.error("Payment failed... Please try again.")
                return

            if gui.button("Cancel", className="border border-danger text-danger me-2"):
                confirm_purchase_modal.close()
            gui.button("Buy", type="primary", key="--confirm-purchase")


def stripe_addon_checkout_redirect(user: AppUser, dollat_amt: int):
    from routers.account import account_route
    from routers.account import payment_processing_route

    line_item = available_subscriptions["addon"]["stripe"].copy()
    line_item["quantity"] = dollat_amt * settings.ADDON_CREDITS_PER_DOLLAR
    checkout_session = stripe.checkout.Session.create(
        line_items=[line_item],
        mode="payment",
        success_url=get_app_route_url(payment_processing_route),
        cancel_url=get_app_route_url(account_route),
        customer=user.get_or_create_stripe_customer(),
        invoice_creation={"enabled": True},
        allow_promotion_codes=True,
        saved_payment_method_options={
            "payment_method_save": "enabled",
        },
    )
    raise gui.RedirectException(checkout_session.url, status_code=303)


def render_stripe_subscription_button(
    *,
    label: str,
    user: AppUser,
    plan: PricingPlan,
    btn_type: str,
    key: str,
):
    if not plan.supports_stripe():
        gui.write("Stripe subscription not available")
        return

    # IMPORTANT: key=... is needed here to maintain uniqueness
    # of buttons with the same label. otherwise, all buttons
    # will be the same to the server
    if gui.button(label, key=key, type=btn_type):
        stripe_subscription_checkout_redirect(user=user, plan=plan)


def stripe_subscription_checkout_redirect(user: AppUser, plan: PricingPlan):
    from routers.account import account_route
    from routers.account import payment_processing_route

    if user.subscription and user.subscription.plan == plan.db_value:
        # already subscribed to some plan
        return

    metadata = {settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD: plan.key}
    checkout_session = stripe.checkout.Session.create(
        line_items=[(plan.get_stripe_line_item())],
        mode="subscription",
        success_url=get_app_route_url(payment_processing_route),
        cancel_url=get_app_route_url(account_route),
        customer=user.get_or_create_stripe_customer(),
        metadata=metadata,
        subscription_data={"metadata": metadata},
        allow_promotion_codes=True,
        saved_payment_method_options={
            "payment_method_save": "enabled",
        },
    )
    raise gui.RedirectException(checkout_session.url, status_code=303)


def render_paypal_subscription_button(
    *,
    plan: PricingPlan,
):
    if not plan.supports_paypal():
        gui.write("Paypal subscription not available")
        return

    lookup_key = plan.key
    gui.html(
        f"""
    <div id="paypal-subscription-{lookup_key}"
         class="paypal-subscription-{lookup_key} paypal-subscription-buttons"
         data-plan-key="{lookup_key}"></div>
    <div id="paypal-result-message"></div>
    """
    )


def render_payment_information(user: AppUser):
    if not user.subscription:
        return

    pm_summary = gui.run_in_thread(
        user.subscription.get_payment_method_summary, cache=True
    )
    if not pm_summary:
        return

    gui.write("## Payment Information", id="payment-information", className="d-block")
    col1, col2, col3 = gui.columns(3, responsive=False)
    with col1:
        gui.write("**Pay via**")
    with col2:
        provider = PaymentProvider(
            user.subscription.payment_provider or PaymentProvider.STRIPE
        )
        gui.write(provider.label)
    with col3:
        if gui.button(f"{icons.edit} Edit", type="link", key="manage-payment-provider"):
            raise gui.RedirectException(user.subscription.get_external_management_url())

    pm_summary = PaymentMethodSummary(*pm_summary)
    if pm_summary.card_brand and pm_summary.card_last4:
        col1, col2, col3 = gui.columns(3, responsive=False)
        with col1:
            gui.write("**Payment Method**")
        with col2:
            gui.write(
                f"{format_card_brand(pm_summary.card_brand)} ending in {pm_summary.card_last4}",
                unsafe_allow_html=True,
            )
        with col3:
            if gui.button(f"{icons.edit} Edit", type="link", key="edit-payment-method"):
                change_payment_method(user)

    if pm_summary.billing_email:
        col1, col2, _ = gui.columns(3, responsive=False)
        with col1:
            gui.write("**Billing Email**")
        with col2:
            gui.html(pm_summary.billing_email)


def change_payment_method(user: AppUser):
    from routers.account import payment_processing_route
    from routers.account import account_route

    match user.subscription.payment_provider:
        case PaymentProvider.STRIPE:
            session = stripe.checkout.Session.create(
                mode="setup",
                currency="usd",
                customer=user.get_or_create_stripe_customer(),
                setup_intent_data={
                    "metadata": {"subscription_id": user.subscription.external_id},
                },
                success_url=get_app_route_url(payment_processing_route),
                cancel_url=get_app_route_url(account_route),
            )
            raise gui.RedirectException(session.url, status_code=303)
        case _:
            gui.error("Not implemented for this payment provider")


def format_card_brand(brand: str) -> str:
    return icons.card_icons.get(brand.lower(), brand.capitalize())


def render_billing_history(user: AppUser, limit: int = 50):
    import pandas as pd

    txns = user.transactions.filter(amount__gt=0).order_by("-created_at")
    if not txns:
        return

    gui.write("## Billing History", className="d-block")
    gui.table(
        pd.DataFrame.from_records(
            [
                {
                    "Date": txn.created_at.strftime("%m/%d/%Y"),
                    "Description": txn.reason_note(),
                    "Amount": f"-${txn.charged_amount / 100:,.2f}",
                    "Credits": f"+{txn.amount:,}",
                    "Balance": f"{txn.end_balance:,}",
                }
                for txn in txns[:limit]
            ]
        ),
    )
    if txns.count() > limit:
        gui.caption(f"Showing only the most recent {limit} transactions.")


def render_auto_recharge_section(user: AppUser):
    assert (
        user.subscription
        and user.subscription.payment_provider == PaymentProvider.STRIPE
    )
    subscription = user.subscription

    gui.write("## Auto Recharge & Limits")
    with gui.div(className="h4"):
        auto_recharge_enabled = gui.checkbox(
            "Enable auto recharge",
            value=subscription.auto_recharge_enabled,
        )

    if auto_recharge_enabled != subscription.auto_recharge_enabled:
        subscription.auto_recharge_enabled = auto_recharge_enabled
        subscription.full_clean()
        subscription.save(update_fields=["auto_recharge_enabled"])

    if not auto_recharge_enabled:
        gui.caption(
            "Enable auto recharge to automatically keep your credit balance topped up."
        )
        return

    col1, col2 = gui.columns(2)
    with col1, gui.div(className="mb-2"):
        subscription.auto_recharge_topup_amount = gui.selectbox(
            "###### Automatically purchase",
            options=settings.ADDON_AMOUNT_CHOICES,
            format_func=lambda amt: f"{settings.ADDON_CREDITS_PER_DOLLAR * int(amt):,} credits for ${amt}",
            value=subscription.auto_recharge_topup_amount,
        )
        subscription.auto_recharge_balance_threshold = gui.selectbox(
            "###### when balance falls below",
            options=settings.AUTO_RECHARGE_BALANCE_THRESHOLD_CHOICES,
            format_func=lambda c: f"{c:,} credits",
            value=subscription.auto_recharge_balance_threshold,
        )

    with col2:
        gui.write("###### Monthly Recharge Budget")
        gui.caption(
            """
            If your account exceeds this budget in a given calendar month,
            subsequent runs & API requests will be rejected.
            """,
        )
        with gui.div(className="d-flex align-items-center"):
            user.subscription.monthly_spending_budget = gui.number_input(
                "",
                min_value=10,
                value=user.subscription.monthly_spending_budget,
                key="monthly-spending-budget",
            )
            gui.write("USD", className="d-block ms-2")

        gui.write("###### Email Notification Threshold")
        gui.caption(
            """
                If your account purchases exceed this threshold in a given
                calendar month, you will receive an email notification.
                """
        )
        with gui.div(className="d-flex align-items-center"):
            user.subscription.monthly_spending_notification_threshold = (
                gui.number_input(
                    "",
                    min_value=10,
                    value=user.subscription.monthly_spending_notification_threshold,
                    key="monthly-spending-notification-threshold",
                )
            )
            gui.write("USD", className="d-block ms-2")

    if gui.button("Save", type="primary", key="save-auto-recharge-and-limits"):
        try:
            subscription.full_clean()
        except ValidationError as e:
            gui.error(str(e))
        else:
            subscription.save()
            gui.success("Settings saved!")


def left_and_right(*, className: str = "", **props):
    className += " d-flex flex-row justify-content-between align-items-center"
    with gui.div(className=className, **props):
        return gui.div(), gui.div()
