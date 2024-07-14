from typing import Literal

import stripe
from django.core.exceptions import ValidationError

import gooey_ui as st
from app_users.models import AppUser, PaymentProvider
from daras_ai_v2 import icons, settings, paypal
from daras_ai_v2.base import RedirectException
from daras_ai_v2.fastapi_tricks import get_route_url
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.settings import templates
from daras_ai_v2.user_date_widgets import render_local_date_attrs
from gooey_ui.components.modal import Modal
from gooey_ui.components.pills import pill
from payments.models import PaymentMethodSummary
from payments.plans import PricingPlan
from scripts.migrate_existing_subscriptions import available_subscriptions

rounded_border = "w-100 border shadow-sm rounded py-4 px-3"


PlanActionLabel = Literal["Upgrade", "Downgrade", "Contact Us", "Your Plan"]


def billing_page(user: AppUser):
    render_payments_setup()

    if user.subscription:
        render_current_plan(user)

    with st.div(className="my-5"):
        render_credit_balance(user)

    with st.div(className="my-5"):
        selected_payment_provider = render_all_plans(user)

    with st.div(className="my-5"):
        render_addon_section(user, selected_payment_provider)

    if user.subscription and user.subscription.payment_provider:
        if user.subscription.payment_provider == PaymentProvider.STRIPE:
            with st.div(className="my-5"):
                render_auto_recharge_section(user)
        with st.div(className="my-5"):
            render_payment_information(user)

    with st.div(className="my-5"):
        render_billing_history(user)


def render_payments_setup():
    from routers.account import payment_processing_route

    st.html(
        templates.get_template("payment_setup.html").render(
            settings=settings,
            payment_processing_url=get_route_url(payment_processing_route),
        )
    )


def render_current_plan(user: AppUser):
    plan = PricingPlan.from_sub(user.subscription)
    provider = (
        PaymentProvider(user.subscription.payment_provider)
        if user.subscription.payment_provider
        else None
    )

    with st.div(className=f"{rounded_border} border-dark"):
        # ROW 1: Plan title and next invoice date
        left, right = left_and_right()
        with left:
            st.write(f"#### Gooey.AI {plan.title}")

            if provider:
                st.write(
                    f"[{icons.edit} Manage Subscription](#payment-information)",
                    unsafe_allow_html=True,
                )
        with right, st.div(className="d-flex align-items-center gap-1"):
            if provider and (
                next_invoice_ts := st.run_in_thread(
                    user.subscription.get_next_invoice_timestamp, cache=True
                )
            ):
                st.html("Next invoice on ")
                pill(
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
            st.write(f"# {plan.pricing_title()}", className="no-margin")
            if plan.monthly_charge:
                provider_text = f" **via {provider.label}**" if provider else ""
                st.caption("per month" + provider_text)

        with right, st.div(className="text-end"):
            st.write(f"# {plan.credits:,} credits", className="no-margin")
            if plan.monthly_charge:
                st.write(
                    f"**${plan.monthly_charge:,}** monthly renewal for {plan.credits:,} credits"
                )


def render_credit_balance(user: AppUser):
    st.write(f"## Credit Balance: {user.balance:,}")
    st.caption(
        "Every time you submit a workflow or make an API call, we deduct credits from your account."
    )


def render_all_plans(user: AppUser) -> PaymentProvider:
    current_plan = (
        PricingPlan.from_sub(user.subscription)
        if user.subscription
        else PricingPlan.STARTER
    )
    all_plans = [plan for plan in PricingPlan if not plan.deprecated]

    st.write("## All Plans")
    plans_div = st.div(className="mb-1")

    if user.subscription and user.subscription.payment_provider:
        selected_payment_provider = None
    else:
        with st.div():
            selected_payment_provider = PaymentProvider[
                payment_provider_radio() or PaymentProvider.STRIPE.name
            ]

    def _render_plan(plan: PricingPlan):
        if plan == current_plan:
            extra_class = "border-dark"
        else:
            extra_class = "bg-light"
        with st.div(className="d-flex flex-column h-100"):
            with st.div(
                className=f"{rounded_border} flex-grow-1 d-flex flex-column p-3 mb-2 {extra_class}"
            ):
                _render_plan_details(plan)
                _render_plan_action_button(
                    user, plan, current_plan, selected_payment_provider
                )

    with plans_div:
        grid_layout(4, all_plans, _render_plan, separator=False)

    with st.div(className="my-2 d-flex justify-content-center"):
        st.caption(f"**[See all features & benefits]({settings.PRICING_DETAILS_URL})**")

    return selected_payment_provider


def _render_plan_details(plan: PricingPlan):
    with st.div(className="flex-grow-1"):
        with st.div(className="mb-4"):
            with st.tag("h4", className="mb-0"):
                st.html(plan.title)
            st.caption(
                plan.description,
                style={
                    "minHeight": "calc(var(--bs-body-line-height) * 2em)",
                    "display": "block",
                },
            )
        with st.div(className="my-3 w-100"):
            with st.tag("h4", className="my-0 d-inline me-2"):
                st.html(plan.pricing_title())
            with st.tag("span", className="text-muted my-0"):
                st.html(plan.pricing_caption())
        st.write(plan.long_description, unsafe_allow_html=True)


def _render_plan_action_button(
    user: AppUser,
    plan: PricingPlan,
    current_plan: PricingPlan,
    payment_provider: PaymentProvider | None,
):
    btn_classes = "w-100 mt-3"
    if plan == current_plan:
        st.button("Your Plan", className=btn_classes, disabled=True, type="tertiary")
    elif plan.contact_us_link:
        with st.link(
            to=plan.contact_us_link,
            className=btn_classes + " btn btn-theme btn-primary",
        ):
            st.html("Contact Us")
    elif user.subscription and not user.subscription.payment_provider:
        # don't show upgrade/downgrade buttons for enterprise customers
        # assumption: anyone without a payment provider attached is admin/enterprise
        return
    else:
        if plan.credits > current_plan.credits:
            label, btn_type = ("Upgrade", "primary")
        else:
            label, btn_type = ("Downgrade", "secondary")

        if user.subscription and user.subscription.payment_provider:
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
            downgrade_modal = Modal(
                "Confirm downgrade",
                key=f"downgrade-plan-modal-{plan.key}",
            )
            if st.button(
                label,
                className=className,
                key=key,
            ):
                downgrade_modal.open()

            if downgrade_modal.is_open():
                with downgrade_modal.container():
                    st.write(
                        f"""
    Are you sure you want to change from:  
    **{current_plan.title} ({fmt_price(current_plan)})** to **{plan.title} ({fmt_price(plan)})**?
                     """,
                        className="d-block py-4",
                    )
                    with st.div(className="d-flex w-100"):
                        if st.button(
                            "Downgrade",
                            className="btn btn-theme bg-danger border-danger text-white",
                            key=f"{key}-confirm",
                        ):
                            change_subscription(user, plan)
                        if st.button(
                            "Cancel",
                            className="border border-danger text-danger",
                            key=f"{key}-cancel",
                        ):
                            downgrade_modal.close()
        case _:
            if st.button(label, className=className, key=key):
                change_subscription(user, plan)


def fmt_price(plan: PricingPlan) -> str:
    if plan.monthly_charge:
        return f"${plan.monthly_charge:,}/month"
    else:
        return "Free"


def change_subscription(user: AppUser, new_plan: PricingPlan):
    from routers.account import account_route
    from routers.account import payment_processing_route

    current_plan = PricingPlan.from_sub(user.subscription)

    if new_plan == current_plan:
        raise RedirectException(get_route_url(account_route), status_code=303)

    if new_plan == PricingPlan.STARTER:
        user.subscription.cancel()
        user.subscription.delete()
        raise RedirectException(
            get_route_url(payment_processing_route), status_code=303
        )

    match user.subscription.payment_provider:
        case PaymentProvider.STRIPE:
            if not new_plan.supports_stripe():
                st.error(f"Stripe subscription not available for {new_plan}")

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
                # charge the full new amount today, without prorations
                # see: https://docs.stripe.com/billing/subscriptions/billing-cycle#reset-the-billing-cycle-to-the-current-time
                billing_cycle_anchor="now",
                proration_behavior="none",
            )
            raise RedirectException(
                get_route_url(payment_processing_route), status_code=303
            )

        case PaymentProvider.PAYPAL:
            if not new_plan.supports_paypal():
                st.error(f"Paypal subscription not available for {new_plan}")

            subscription = paypal.Subscription.retrieve(user.subscription.external_id)
            paypal_plan_info = new_plan.get_paypal_plan()
            approval_url = subscription.update_plan(
                plan_id=paypal_plan_info["plan_id"],
                plan=paypal_plan_info["plan"],
            )
            raise RedirectException(approval_url, status_code=303)

        case _:
            st.error("Not implemented for this payment provider")


def payment_provider_radio(**props) -> str | None:
    with st.div(className="d-flex"):
        st.write("###### Pay Via", className="d-block me-3")
        return st.radio(
            "",
            options=PaymentProvider.names,
            format_func=lambda name: f'<span class="me-3">{PaymentProvider[name].label}</span>',
            **props,
        )


def render_addon_section(user: AppUser, selected_payment_provider: PaymentProvider):
    if user.subscription:
        st.write("# Purchase More Credits")
    else:
        st.write("# Purchase Credits")
    st.caption(f"Buy more credits. $1 per {settings.ADDON_CREDITS_PER_DOLLAR} credits")

    if user.subscription:
        provider = PaymentProvider(user.subscription.payment_provider)
    else:
        provider = selected_payment_provider
    match provider:
        case PaymentProvider.STRIPE:
            render_stripe_addon_buttons(user)
        case PaymentProvider.PAYPAL:
            render_paypal_addon_buttons()


def render_paypal_addon_buttons():
    selected_amt = st.horizontal_radio(
        "",
        settings.ADDON_AMOUNT_CHOICES,
        format_func=lambda amt: f"${amt:,}",
        checked_by_default=False,
    )
    if selected_amt:
        st.js(
            f"setPaypalAddonQuantity({int(selected_amt) * settings.ADDON_CREDITS_PER_DOLLAR})"
        )
    st.div(
        id="paypal-addon-buttons",
        className="mt-2",
        style={"width": "fit-content"},
    )
    st.div(id="paypal-result-message")


def render_stripe_addon_buttons(user: AppUser):
    for dollat_amt in settings.ADDON_AMOUNT_CHOICES:
        render_stripe_addon_button(dollat_amt, user)


def render_stripe_addon_button(dollat_amt: int, user: AppUser):
    confirm_purchase_modal = Modal(
        "Confirm Purchase", key=f"confirm-purchase-{dollat_amt}"
    )
    if st.button(f"${dollat_amt:,}", type="primary"):
        if user.subscription:
            confirm_purchase_modal.open()
        else:
            from routers.account import account_route
            from routers.account import payment_processing_route

            line_item = available_subscriptions["addon"]["stripe"].copy()
            line_item["quantity"] = dollat_amt * settings.ADDON_CREDITS_PER_DOLLAR

            checkout_session = stripe.checkout.Session.create(
                line_items=[line_item],
                mode="payment",
                success_url=get_route_url(payment_processing_route),
                cancel_url=get_route_url(account_route),
                customer=user.get_or_create_stripe_customer(),
                invoice_creation={"enabled": True},
                allow_promotion_codes=True,
            )
            raise RedirectException(checkout_session.url, status_code=303)

    if not confirm_purchase_modal.is_open():
        return
    with confirm_purchase_modal.container():
        st.write(
            f"""
                Please confirm your purchase:  
                 **{dollat_amt * settings.ADDON_CREDITS_PER_DOLLAR:,} credits for ${dollat_amt}**.
                 """,
            className="py-4 d-block text-center",
        )
        with st.div(className="d-flex w-100 justify-content-end"):
            if st.session_state.get("--confirm-purchase"):
                success = st.run_in_thread(
                    user.subscription.stripe_attempt_addon_purchase,
                    args=[dollat_amt],
                    placeholder="Processing payment...",
                )
                if success is None:
                    return
                st.session_state.pop("--confirm-purchase")
                if success:
                    confirm_purchase_modal.close()
                else:
                    st.error("Payment failed... Please try again.")
                return

            if st.button("Cancel", className="border border-danger text-danger me-2"):
                confirm_purchase_modal.close()
            st.button("Buy", type="primary", key="--confirm-purchase")


def render_stripe_subscription_button(
    *,
    label: str,
    user: AppUser,
    plan: PricingPlan,
    btn_type: str,
    key: str,
):
    if not plan.supports_stripe():
        st.write("Stripe subscription not available")
        return

    # IMPORTANT: key=... is needed here to maintain uniqueness
    # of buttons with the same label. otherwise, all buttons
    # will be the same to the server
    if st.button(label, key=key, type=btn_type):
        create_stripe_checkout_session(user=user, plan=plan)


def create_stripe_checkout_session(user: AppUser, plan: PricingPlan):
    from routers.account import account_route
    from routers.account import payment_processing_route

    if user.subscription:
        # already subscribed to some plan
        return

    metadata = {settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD: plan.key}
    checkout_session = stripe.checkout.Session.create(
        line_items=[(plan.get_stripe_line_item())],
        mode="subscription",
        success_url=get_route_url(payment_processing_route),
        cancel_url=get_route_url(account_route),
        customer=user.get_or_create_stripe_customer(),
        metadata=metadata,
        subscription_data={"metadata": metadata},
        allow_promotion_codes=True,
        saved_payment_method_options={
            "payment_method_save": "enabled",
        },
    )
    raise RedirectException(checkout_session.url, status_code=303)


def render_paypal_subscription_button(
    *,
    plan: PricingPlan,
):
    if not plan.supports_paypal():
        st.write("Paypal subscription not available")
        return

    lookup_key = plan.key
    st.html(
        f"""
    <div id="paypal-subscription-{lookup_key}"
         class="paypal-subscription-{lookup_key} paypal-subscription-buttons"
         data-plan-key="{lookup_key}"></div>
    <div id="paypal-result-message"></div>
    """
    )


def render_payment_information(user: AppUser):
    assert user.subscription

    st.write("## Payment Information", id="payment-information", className="d-block")
    col1, col2, col3 = st.columns(3, responsive=False)
    with col1:
        st.write("**Pay via**")
    with col2:
        provider = PaymentProvider(user.subscription.payment_provider)
        st.write(provider.label)
    with col3:
        if st.button(f"{icons.edit} Edit", type="link", key="manage-payment-provider"):
            raise RedirectException(user.subscription.get_external_management_url())

    pm_summary = st.run_in_thread(
        user.subscription.get_payment_method_summary, cache=True
    )
    if not pm_summary:
        return
    pm_summary = PaymentMethodSummary(*pm_summary)
    if pm_summary.card_brand and pm_summary.card_last4:
        col1, col2, col3 = st.columns(3, responsive=False)
        with col1:
            st.write("**Payment Method**")
        with col2:
            st.write(
                f"{format_card_brand(pm_summary.card_brand)} ending in {pm_summary.card_last4}",
                unsafe_allow_html=True,
            )
        with col3:
            if st.button(f"{icons.edit} Edit", type="link", key="edit-payment-method"):
                change_payment_method(user)

    if pm_summary.billing_email:
        col1, col2, _ = st.columns(3, responsive=False)
        with col1:
            st.write("**Billing Email**")
        with col2:
            st.html(pm_summary.billing_email)


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
                success_url=get_route_url(payment_processing_route),
                cancel_url=get_route_url(account_route),
            )
            raise RedirectException(session.url, status_code=303)
        case _:
            st.error("Not implemented for this payment provider")


def format_card_brand(brand: str) -> str:
    return icons.card_icons.get(brand.lower(), brand.capitalize())


def render_billing_history(user: AppUser, limit: int = 50):
    import pandas as pd

    txns = user.transactions.filter(amount__gt=0).order_by("-created_at")
    if not txns:
        return

    st.write("## Billing History", className="d-block")
    st.table(
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
        st.caption(f"Showing only the most recent {limit} transactions.")


def render_auto_recharge_section(user: AppUser):
    assert (
        user.subscription
        and user.subscription.payment_provider == PaymentProvider.STRIPE
    )
    subscription = user.subscription

    st.write("## Auto Recharge & Limits")
    with st.div(className="h4"):
        auto_recharge_enabled = st.checkbox(
            "Enable auto recharge",
            value=subscription.auto_recharge_enabled,
        )

    if auto_recharge_enabled != subscription.auto_recharge_enabled:
        subscription.auto_recharge_enabled = auto_recharge_enabled
        subscription.full_clean()
        subscription.save(update_fields=["auto_recharge_enabled"])

    if not auto_recharge_enabled:
        st.caption(
            "Enable auto recharge to automatically keep your credit balance topped up."
        )
        return

    col1, col2 = st.columns(2)
    with col1, st.div(className="mb-2"):
        subscription.auto_recharge_topup_amount = st.selectbox(
            "###### Automatically purchase",
            options=settings.ADDON_AMOUNT_CHOICES,
            format_func=lambda amt: f"{settings.ADDON_CREDITS_PER_DOLLAR * int(amt):,} credits for ${amt}",
            value=subscription.auto_recharge_topup_amount,
        )
        subscription.auto_recharge_balance_threshold = st.selectbox(
            "###### when balance falls below",
            options=settings.AUTO_RECHARGE_BALANCE_THRESHOLD_CHOICES,
            format_func=lambda c: f"{c:,} credits",
            value=subscription.auto_recharge_balance_threshold,
        )

    with col2:
        st.write("###### Monthly Recharge Budget")
        st.caption(
            """
            If your account exceeds this budget in a given calendar month,
            subsequent runs & API requests will be rejected.
            """,
        )
        with st.div(className="d-flex align-items-center"):
            user.subscription.monthly_spending_budget = st.number_input(
                "",
                min_value=10,
                value=user.subscription.monthly_spending_budget,
                key="monthly-spending-budget",
            )
            st.write("USD", className="d-block ms-2")

        st.write("###### Email Notification Threshold")
        st.caption(
            """
                If your account purchases exceed this threshold in a given
                calendar month, you will receive an email notification.
                """
        )
        with st.div(className="d-flex align-items-center"):
            user.subscription.monthly_spending_notification_threshold = st.number_input(
                "",
                min_value=10,
                value=user.subscription.monthly_spending_notification_threshold,
                key="monthly-spending-notification-threshold",
            )
            st.write("USD", className="d-block ms-2")

    if st.button("Save", type="primary", key="save-auto-recharge-and-limits"):
        try:
            subscription.full_clean()
        except ValidationError as e:
            st.error(str(e))
        else:
            subscription.save()
            st.success("Settings saved!")


def left_and_right(*, className: str = "", **props):
    className += " d-flex flex-row justify-content-between align-items-center"
    with st.div(className=className, **props):
        return st.div(), st.div()
