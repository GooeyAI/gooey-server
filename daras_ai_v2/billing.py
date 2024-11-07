import typing

import gooey_gui as gui
import sentry_sdk
import stripe
from django.core.exceptions import ValidationError
from loguru import logger

from app_users.models import AppUserTransaction, PaymentProvider
from daras_ai_v2 import icons, settings, paypal
from daras_ai_v2.fastapi_tricks import get_app_route_url
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.html_spinner_widget import html_spinner
from daras_ai_v2.settings import templates
from daras_ai_v2.user_date_widgets import render_local_date_attrs
from payments.models import PaymentMethodSummary
from payments.plans import PricingPlan
from payments.webhooks import StripeWebhookHandler, set_workspace_subscription
from scripts.migrate_existing_subscriptions import available_subscriptions

if typing.TYPE_CHECKING:
    from workspaces.models import Workspace


rounded_border = "w-100 border shadow-sm rounded py-4 px-3"


def billing_page(workspace: "Workspace"):
    from daras_ai_v2.base import BasePage

    render_payments_setup()

    if not workspace.is_personal:
        with gui.div(className="mb-3"):
            BasePage.render_author(workspace, show_as_link=False)

    if workspace.subscription and workspace.subscription.is_paid():
        with gui.div(className="mb-5"):
            render_current_plan(workspace)

    with gui.div(className="mb-5"):
        render_credit_balance(workspace)

    with gui.div(className="mb-5"):
        selected_payment_provider = render_all_plans(workspace)

    with gui.div(className="mb-5"):
        render_addon_section(workspace, selected_payment_provider)

    if workspace.subscription:
        if workspace.subscription.payment_provider == PaymentProvider.STRIPE:
            with gui.div(className="mb-5"):
                render_auto_recharge_section(workspace)

        with gui.div(className="mb-5"):
            render_payment_information(workspace)

    with gui.div(className="mb-5"):
        render_billing_history(workspace)


def render_payments_setup():
    from routers.account import payment_processing_route

    gui.html(
        templates.get_template("payment_setup.html").render(
            settings=settings,
            payment_processing_url=get_app_route_url(payment_processing_route),
        )
    )


def render_current_plan(workspace: "Workspace"):
    plan = PricingPlan.from_sub(workspace.subscription)
    if workspace.subscription.payment_provider:
        provider = PaymentProvider(workspace.subscription.payment_provider)
    else:
        provider = None

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
                    workspace.subscription.get_next_invoice_timestamp, cache=True
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
                if provider:
                    provider_text = f" **via {provider.label}**"
                else:
                    provider_text = ""
                gui.caption("per month" + provider_text)

        with right, gui.div(className="text-end"):
            gui.write(f"# {plan.credits:,} credits", className="no-margin")
            if plan.monthly_charge:
                gui.write(
                    f"**${plan.monthly_charge:,}** monthly renewal for {plan.credits:,} credits"
                )


def render_credit_balance(workspace: "Workspace"):
    gui.write(f"## Credit Balance: {workspace.balance:,}")
    gui.caption(
        "Every time you submit a workflow or make an API call, we deduct credits from your account."
    )


def render_all_plans(workspace: "Workspace") -> PaymentProvider:
    current_plan = (
        PricingPlan.from_sub(workspace.subscription)
        if workspace.subscription
        else PricingPlan.STARTER
    )
    all_plans = [plan for plan in PricingPlan if not plan.deprecated]

    gui.write("## All Plans")
    plans_div = gui.div(className="mb-1")

    if workspace.subscription and workspace.subscription.payment_provider:
        selected_payment_provider = workspace.subscription.payment_provider
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
                    workspace=workspace,
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
    workspace: "Workspace",
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
        workspace.subscription
        and workspace.subscription.plan == PricingPlan.ENTERPRISE.db_value
    ):
        # don't show upgrade/downgrade buttons for enterprise customers
        return
    elif workspace.subscription and workspace.subscription.is_paid():
        render_change_subscription_button(
            workspace=workspace, plan=plan, current_plan=current_plan
        )
    else:
        assert payment_provider is not None  # for sanity
        _render_create_subscription_button(
            workspace=workspace,
            plan=plan,
            payment_provider=payment_provider,
        )


def render_change_subscription_button(
    *,
    workspace: "Workspace",
    plan: PricingPlan,
    current_plan: PricingPlan,
):
    # subscription exists, show upgrade/downgrade button
    if plan.credits > current_plan.credits:
        ref = gui.use_confirm_dialog(key=f"--modal-{plan.key}")
        gui.button_with_confirm_dialog(
            ref=ref,
            trigger_label="Upgrade",
            trigger_type="primary",
            modal_title="#### Upgrade Plan",
            modal_content=f"""
Are you sure you want to upgrade from **{current_plan.title} @ {fmt_price(current_plan)}** to **{plan.title} @ {fmt_price(plan)}**?

Your payment method will be charged ${plan.monthly_charge:,} today and again every month until you cancel.

**{plan.credits:,} Credits** will be added to your account today and with subsequent payments, your account balance
will be refreshed to {plan.credits:,} Credits.
                """,
            confirm_label="Upgrade",
        )
        if ref.pressed_confirm:
            try:
                change_subscription(
                    workspace,
                    plan,
                    # when upgrading, charge the full new amount today: https://docs.stripe.com/billing/subscriptions/billing-cycle#reset-the-billing-cycle-to-the-current-time
                    billing_cycle_anchor="now",
                    payment_behavior="error_if_incomplete",
                )
            except (stripe.CardError, stripe.InvalidRequestError) as e:
                if isinstance(e, stripe.InvalidRequestError):
                    sentry_sdk.capture_exception(e)
                    logger.warning(e)

                # only handle error if it's related to mandates
                # cancel current subscription & redirect user to new subscription page
                workspace.subscription.cancel()
                stripe_subscription_create(workspace, plan)
    else:
        ref = gui.use_confirm_dialog(key=f"--modal-{plan.key}")
        gui.button_with_confirm_dialog(
            ref=ref,
            trigger_label="Downgrade",
            modal_title="#### Downgrade Plan",
            modal_content=f"""
Are you sure you want to downgrade from: **{current_plan.title} @ {fmt_price(current_plan)}** to **{plan.title} @ {fmt_price(plan)}**?

This will take effect from the next billing cycle.
                """,
            confirm_label="Downgrade",
            confirm_className="border-danger bg-danger text-white",
        )
        if ref.pressed_confirm:
            change_subscription(workspace, plan)


def _render_create_subscription_button(
    *,
    workspace: "Workspace",
    plan: PricingPlan,
    payment_provider: PaymentProvider,
):
    match payment_provider:
        case PaymentProvider.STRIPE:
            render_stripe_subscription_button(workspace=workspace, plan=plan)
        case PaymentProvider.PAYPAL:
            render_paypal_subscription_button(plan=plan)


def fmt_price(plan: PricingPlan) -> str:
    if plan.monthly_charge:
        return f"${plan.monthly_charge:,}/month"
    else:
        return "Free"


def change_subscription(workspace: "Workspace", new_plan: PricingPlan, **kwargs):
    from routers.account import account_route
    from routers.account import payment_processing_route

    current_plan = PricingPlan.from_sub(workspace.subscription)

    if new_plan == current_plan:
        raise gui.RedirectException(get_app_route_url(account_route), status_code=303)

    if new_plan == PricingPlan.STARTER:
        workspace.subscription.cancel()
        raise gui.RedirectException(
            get_app_route_url(payment_processing_route), status_code=303
        )

    match workspace.subscription.payment_provider:
        case PaymentProvider.STRIPE:
            if not new_plan.supports_stripe():
                gui.error(f"Stripe subscription not available for {new_plan}")

            subscription = stripe.Subscription.retrieve(
                workspace.subscription.external_id
            )
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

            subscription = paypal.Subscription.retrieve(
                workspace.subscription.external_id
            )
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


def render_addon_section(
    workspace: "Workspace", selected_payment_provider: PaymentProvider
):
    if workspace.subscription:
        gui.write("# Purchase More Credits")
    else:
        gui.write("# Purchase Credits")
    gui.caption(f"Buy more credits. $1 per {settings.ADDON_CREDITS_PER_DOLLAR} credits")

    if workspace.subscription and workspace.subscription.payment_provider:
        provider = PaymentProvider(workspace.subscription.payment_provider)
    else:
        provider = selected_payment_provider
    match provider:
        case PaymentProvider.STRIPE:
            render_stripe_addon_buttons(workspace)
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


def render_stripe_addon_buttons(workspace: "Workspace"):
    if not (workspace.subscription and workspace.subscription.payment_provider):
        save_pm = gui.checkbox(
            "Save payment method for future purchases & auto-recharge", value=True
        )
    else:
        save_pm = True

    for dollat_amt in settings.ADDON_AMOUNT_CHOICES:
        render_stripe_addon_button(dollat_amt, workspace, save_pm)


def render_stripe_addon_button(dollat_amt: int, workspace: "Workspace", save_pm: bool):
    ref = gui.use_confirm_dialog(
        key=f"addon-confirm-dialog-{dollat_amt}", close_on_confirm=False
    )

    if gui.button(
        key=f"addon-button-{dollat_amt}", label=f"${dollat_amt:,}", type="primary"
    ):
        if (
            workspace.subscription
            and workspace.subscription.stripe_get_default_payment_method()
        ):
            ref.set_open(True)
        else:
            stripe_addon_checkout_redirect(workspace, dollat_amt, save_pm)
            return

    if not ref.is_open:
        return

    if ref.pressed_confirm:
        gui.session_state["processing-payment"] = True

    if not gui.session_state.get("processing-payment"):
        gui.confirm_dialog(
            ref=ref,
            modal_title="#### Purchase Credits",
            modal_content=f"""
Please confirm your purchase of **{dollat_amt * settings.ADDON_CREDITS_PER_DOLLAR:,} Credits for ${dollat_amt}**.

This is a one-time purchase and your account will be credited once the payment is made.
            """,
            confirm_label="Buy",
        )
        return

    header, body, footer = gui.modal_scaffold()
    with header:
        gui.write("#### Purchase Credits")
    with body, gui.center():
        html_spinner("Processing Payment...")
        success = gui.run_in_thread(
            workspace.subscription.stripe_attempt_addon_purchase,
            args=[dollat_amt],
            placeholder="",
        )
        if success is None:
            # thread is running
            return

    ref.set_open(False)
    gui.session_state.pop("processing-payment", None)

    if success:
        # close dialog
        raise gui.RerunException()
    else:
        # fallback to stripe checkout flow if the auto payment failed
        stripe_addon_checkout_redirect(workspace, dollat_amt, save_pm)


def stripe_addon_checkout_redirect(
    workspace: "Workspace", dollat_amt: int, save_pm: bool
):
    from routers.account import account_route
    from routers.account import payment_processing_route

    line_item = available_subscriptions["addon"]["stripe"].copy()
    line_item["quantity"] = dollat_amt * settings.ADDON_CREDITS_PER_DOLLAR
    kwargs = {}
    if save_pm:
        kwargs["payment_intent_data"] = {"setup_future_usage": "on_session"}
    else:
        kwargs["saved_payment_method_options"] = {"payment_method_save": "enabled"}
    checkout_session = stripe.checkout.Session.create(
        line_items=[line_item],
        mode="payment",
        success_url=get_app_route_url(payment_processing_route),
        cancel_url=get_app_route_url(account_route),
        customer=workspace.get_or_create_stripe_customer(),
        invoice_creation={"enabled": True},
        allow_promotion_codes=True,
        **kwargs,
    )
    raise gui.RedirectException(checkout_session.url, status_code=303)


def render_stripe_subscription_button(
    *,
    workspace: "Workspace",
    plan: PricingPlan,
):
    if not plan.supports_stripe():
        gui.write("Stripe subscription not available")
        return

    ref = gui.use_confirm_dialog(key=f"--change-sub-confirm-dialog-{plan.key}")

    if gui.button(key=f"--change-sub-{plan.key}", label="Upgrade", type="primary"):
        if (
            workspace.subscription
            and workspace.subscription.stripe_get_default_payment_method()
        ):
            ref.set_open(True)
        else:
            stripe_subscription_create(workspace=workspace, plan=plan)

    if ref.is_open:
        gui.confirm_dialog(
            ref=ref,
            modal_title="#### Upgrade Plan",
            confirm_label="Buy",
            modal_content=f"""
Are you sure you want to subscribe to **{plan.title} ({fmt_price(plan)})**?

This will charge you the full amount today, and every month thereafter.

**{plan.credits:,} credits** will be added to your account.
            """,
        )

    if ref.pressed_confirm:
        stripe_subscription_create(workspace=workspace, plan=plan)


def stripe_subscription_create(workspace: "Workspace", plan: PricingPlan):
    from routers.account import account_route
    from routers.account import payment_processing_route

    if workspace.subscription and workspace.subscription.is_paid():
        # sanity check: already subscribed to some plan
        gui.rerun()

    # check for existing subscriptions on stripe
    customer = workspace.get_or_create_stripe_customer()
    for sub in stripe.Subscription.list(
        customer=customer, status="active", limit=1
    ).data:
        StripeWebhookHandler.handle_subscription_updated(workspace, sub)
        raise gui.RedirectException(
            get_app_route_url(payment_processing_route), status_code=303
        )

    # try to directly create the subscription without checkout
    pm = (
        workspace.subscription
        and workspace.subscription.stripe_get_default_payment_method()
    )
    metadata = {settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD: plan.key}
    line_items = [plan.get_stripe_line_item()]
    if pm:
        sub = stripe.Subscription.create(
            customer=pm.customer,
            items=line_items,
            metadata=metadata,
            default_payment_method=pm.id,
            proration_behavior="none",
        )
        if sub.status != "incomplete":
            # if the call succeeded redirect, otherwise use the checkout flow
            raise gui.RedirectException(
                get_app_route_url(payment_processing_route), status_code=303
            )

    # redirect to stripe checkout flow
    checkout_session = stripe.checkout.Session.create(
        mode="subscription",
        success_url=get_app_route_url(payment_processing_route),
        cancel_url=get_app_route_url(account_route),
        allow_promotion_codes=True,
        customer=customer,
        line_items=line_items,
        metadata=metadata,
        subscription_data={"metadata": metadata},
        saved_payment_method_options={"payment_method_save": "enabled"},
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


def render_payment_information(workspace: "Workspace"):
    if not workspace.subscription:
        return

    pm_summary = gui.run_in_thread(
        workspace.subscription.get_payment_method_summary, cache=True
    )
    if not pm_summary:
        return

    gui.write("## Payment Information", id="payment-information", className="d-block")
    with gui.div(className="ps-1"):
        col1, col2, col3 = gui.columns(3, responsive=False)
        with col1:
            gui.write("**Pay via**")
        with col2:
            provider = PaymentProvider(
                workspace.subscription.payment_provider or PaymentProvider.STRIPE
            )
            gui.write(provider.label)
        with col3:
            if gui.button(
                f"{icons.edit} Edit", type="link", key="manage-payment-provider"
            ):
                raise gui.RedirectException(
                    workspace.subscription.get_external_management_url()
                )

        pm_summary = PaymentMethodSummary(*pm_summary)
        if pm_summary.card_brand:
            col1, col2, col3 = gui.columns(3, responsive=False)
            with col1:
                gui.write("**Payment Method**")
            with col2:
                if pm_summary.card_last4:
                    gui.write(
                        f"{format_card_brand(pm_summary.card_brand)} ending in {pm_summary.card_last4}",
                        unsafe_allow_html=True,
                    )
                else:
                    gui.write(pm_summary.card_brand)
            with col3:
                if gui.button(
                    f"{icons.edit} Edit", type="link", key="edit-payment-method"
                ):
                    change_payment_method(workspace)

        if pm_summary.billing_email:
            col1, col2, _ = gui.columns(3, responsive=False)
            with col1:
                gui.write("**Billing Email**")
            with col2:
                gui.html(pm_summary.billing_email)

    from routers.account import payment_processing_route

    ref = gui.use_confirm_dialog(key="--delete-payment-method")
    gui.button_with_confirm_dialog(
        ref=ref,
        trigger_label="Delete & Cancel Subscription",
        trigger_className="border-danger text-danger",
        modal_title="#### Delete Payment Information",
        modal_content="""
Are you sure you want to delete your payment information?

This will cancel your subscription and remove your saved payment method.
        """,
        confirm_label="Delete",
        confirm_className="border-danger bg-danger text-white",
    )
    if ref.pressed_confirm:
        set_workspace_subscription(
            workspace=workspace,
            plan=PricingPlan.STARTER,
            provider=None,
            external_id=None,
        )
        pm = (
            workspace.subscription
            and workspace.subscription.stripe_get_default_payment_method()
        )
        if pm:
            pm.detach()
        raise gui.RedirectException(
            get_app_route_url(payment_processing_route), status_code=303
        )


def change_payment_method(workspace: "Workspace"):
    from routers.account import payment_processing_route
    from routers.account import account_route

    match workspace.subscription.payment_provider:
        case PaymentProvider.STRIPE:
            session = stripe.checkout.Session.create(
                mode="setup",
                currency="usd",
                customer=workspace.get_or_create_stripe_customer(),
                setup_intent_data={
                    "metadata": {"subscription_id": workspace.subscription.external_id},
                },
                success_url=get_app_route_url(payment_processing_route),
                cancel_url=get_app_route_url(account_route),
            )
            raise gui.RedirectException(session.url, status_code=303)
        case _:
            gui.error("Not implemented for this payment provider")


def format_card_brand(brand: str) -> str:
    return icons.card_icons.get(brand.lower(), brand.capitalize())


def render_billing_history(workspace: "Workspace", limit: int = 50):
    import pandas as pd

    txns = AppUserTransaction.objects.filter(
        workspace=workspace, amount__gt=0
    ).order_by("-created_at")
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


def render_auto_recharge_section(workspace: "Workspace"):
    assert workspace.subscription
    subscription = workspace.subscription

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
            subscription.monthly_spending_budget = gui.number_input(
                "",
                min_value=10,
                value=subscription.monthly_spending_budget,
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
            subscription.monthly_spending_notification_threshold = gui.number_input(
                "",
                min_value=10,
                value=subscription.monthly_spending_notification_threshold,
                key="monthly-spending-notification-threshold",
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
