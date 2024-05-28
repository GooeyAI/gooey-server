from textwrap import dedent

from django.core.exceptions import ValidationError
from django.db import transaction
from furl import furl

import gooey_ui as st
from app_users.models import AppUser, PaymentProvider
from daras_ai_v2 import icons, settings
from daras_ai_v2.base import RedirectException
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.settings import templates
from gooey_ui.components.modal import Modal
from gooey_ui.components.pills import pill
from payments.plans import PricingPlan


payment_processing_url = str(
    furl(settings.APP_BASE_URL) / settings.PAYMENT_PROCESSING_PAGE_PATH
)
stripe_create_checkout_session_url = "/__/stripe/create-checkout-session"
change_subscription_url = "/__/billing/change-subscription"
change_payment_method_url = "/__/billing/change-payment-method"


def billing_page(user: AppUser):
    render_payments_setup()

    if user.subscription:
        render_current_plan(user)

    with st.div(className="my-5"):
        render_credit_balance(user)

    with st.div(className="my-5"):
        render_all_plans(user)

    if user.subscription:
        if user.subscription.payment_provider == PaymentProvider.STRIPE:
            with st.div(className="my-5"):
                render_auto_recharge_section(user)
        with st.div(className="my-5"):
            render_addon_section(user)
        with st.div(className="my-5"):
            render_payment_information(user)

    with st.div(className="my-5"):
        render_billing_history(user)

    return


def render_payments_setup():
    st.html(templates.get_template("payment_setup.html").render(settings=settings))


def render_current_plan(user: AppUser):
    subscription = user.subscription
    plan = PricingPlan(subscription.plan)
    with border_box(className="w-100 pt-4 p-3 text-dark border-dark"):
        left, right = left_and_right(className="align-items-center")
        with left:
            st.write(
                dedent(
                    f"""
                #### Gooey.AI {plan.title}

                [{icons.edit} Manage Subscription](#payment-information)
                """
                ),
                unsafe_allow_html=True,
            )
        if plan.monthly_charge:
            if next_invoice_date := subscription.get_next_invoice_date():
                with right, st.tag("p", className="text-muted"):
                    st.html("Next invoice on ")
                    pill(next_invoice_date.strftime("%b %d, %Y"), type="dark")

        left, right = left_and_right(className="mt-5")
        with left:
            with st.tag("h1", className="my-0"):
                st.html(plan.pricing_title())
            if plan.monthly_charge:
                provider = PaymentProvider(subscription.payment_provider)
                with st.div(className="d-flex align-items-center"):
                    st.caption(
                        f"per month **via {provider.label}**", unsafe_allow_html=True
                    )
        with right, st.tag("div", className="text-end"):
            with st.tag("h1", className="my-0"):
                st.html(f"{plan.credits:,} credits")
            if plan.monthly_charge:
                st.write(
                    f"**${plan.monthly_charge:,}** monthly renewal for {plan.credits:,} credits"
                )


def render_credit_balance(user: AppUser):
    st.write(f"## Credit Balance: {user.balance:,}")
    st.caption(
        "Every time you submit a workflow or make an API call, we deduct credits from your account."
    )


def render_all_plans(user: AppUser):
    current_plan = (
        PricingPlan(user.subscription.plan)
        if user.subscription
        else PricingPlan.STARTER
    )
    all_plans = [plan for plan in PricingPlan if not plan.deprecated]

    def _payment_provider_radio(className: str = "", **props) -> PaymentProvider:
        with st.div(className=className):
            return PaymentProvider[
                payment_provider_radio(**props) or PaymentProvider.STRIPE.name
            ]

    st.write("## All Plans")
    plans_div = st.div(className="mb-1")
    payment_provider = _payment_provider_radio() if not user.subscription else None

    def _render_plan(plan: PricingPlan):
        nonlocal payment_provider

        extra_class = "border-dark" if plan == current_plan else "bg-light"
        with st.div(className="d-flex flex-column h-100"):
            with border_box(
                className=f"flex-grow-1 d-flex flex-column p-3 mb-2 {extra_class}"
            ):
                _render_plan_details(plan)
                _render_plan_action_button(plan, current_plan, payment_provider)

    with plans_div:
        grid_layout(4, all_plans, _render_plan, separator=False)
    with st.div(className="my-2 d-flex justify-content-center"):
        st.caption(
            f"**[See all features & benefits]({furl(settings.APP_BASE_URL)/'pricing'/''})**"
        )


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
    else:
        update_subscription_button(
            plan=plan,
            current_plan=current_plan,
            className=btn_classes,
            payment_provider=payment_provider,
        )


def update_subscription_button(
    *,
    current_plan: PricingPlan,
    plan: PricingPlan,
    className: str = "",
    payment_provider: PaymentProvider | None = None,
):
    label, type = (
        ("Upgrade", "primary")
        if plan.credits > current_plan.credits
        else ("Downgrade", "secondary")
    )
    className += f" btn btn-theme btn-{type}"

    match payment_provider:
        case PaymentProvider.STRIPE:
            render_stripe_subscription_button(
                label, plan=plan, className=className, type=type
            )
        case PaymentProvider.PAYPAL:
            render_paypal_subscription_button(plan=plan)
        case _ if label == "Downgrade":
            downgrade_modal = Modal(
                "Confirm downgrade",
                key=f"downgrade-plan-modal-{plan.key}",
            )
            if st.button(
                label, className=className, key=f"downgrade-button-{plan.key}"
            ):
                downgrade_modal.open()

            if downgrade_modal.is_open():
                with downgrade_modal.container():
                    fmt_price = lambda plan: (
                        f"${plan.monthly_charge:,}/month"
                        if plan.monthly_charge
                        else "Free"
                    )
                    st.write(
                        f"""
    Are you sure you want to change from:  
    **{current_plan.title} ({fmt_price(current_plan)})** to **{plan.title} ({fmt_price(plan)})**?
                     """,
                        className="d-block py-4",
                    )
                    with st.div(className="d-flex w-100"):
                        render_change_subscription_button(
                            "Downgrade",
                            plan=plan,
                            className="btn btn-theme bg-danger border-danger text-white",
                        )
                        if st.button(
                            "Cancel", className="border border-danger text-danger"
                        ):
                            downgrade_modal.close()
        case _:
            render_change_subscription_button(label, plan=plan, className=className)


def render_change_subscription_button(label: str, *, plan: PricingPlan, className: str):
    st.html(
        f"""
    <form action="{change_subscription_url}" method="post" class="d-inline">
        <input type="hidden" name="lookup_key" value="{plan.key}">
        <button type="submit" class="{className}" data-submit-disabled>{label}</button>
    </form>
    """
    )


def payment_provider_radio(**props) -> str | None:
    with st.div(className="d-flex"):
        st.write("###### Pay Via", className="d-block me-3")
        return st.radio(
            "",
            options=PaymentProvider.names,
            format_func=lambda name: f'<span class="me-3">{PaymentProvider[name].label}</span>',
            **props,
        )


def render_addon_section(user: AppUser):
    assert user.subscription

    st.write("# Purchase More Credits")
    st.caption(f"Buy more credits. $1 per {settings.ADDON_CREDITS_PER_DOLLAR} credits")

    provider = PaymentProvider(user.subscription.payment_provider)
    match provider:
        case PaymentProvider.STRIPE:
            for amount in settings.ADDON_AMOUNT_CHOICES:
                render_stripe_addon_button(amount, user=user)
        case PaymentProvider.PAYPAL:
            for amount in settings.ADDON_AMOUNT_CHOICES:
                render_paypal_addon_button(amount)
            st.div(
                id="paypal-addon-buttons",
                className="mt-2",
                style={"width": "fit-content"},
            )
            st.div(id="paypal-result-message")


def render_paypal_addon_button(amount: int):
    st.html(
        f"""
    <button class="streamlit-like-btn paypal-checkout-option"
            onClick="setPaypalAddonQuantity({amount * settings.ADDON_CREDITS_PER_DOLLAR});"
            type="button"
            data-submit-disabled
    >${amount:,}</button>
    """
    )


def render_stripe_addon_button(amount: int, user: AppUser):
    confirm_purchase_modal = Modal("Confirm Purchase", key=f"confirm-purchase-{amount}")
    if st.button(f"${amount:,}", type="primary"):
        confirm_purchase_modal.open()

    if confirm_purchase_modal.is_open():
        with confirm_purchase_modal.container():
            st.write(
                f"""
                Please confirm your purchase:  
                 **{amount * settings.ADDON_CREDITS_PER_DOLLAR:,} credits for ${amount}**.
             """,
                className="py-4 d-block",
            )
            with st.div(className="d-flex w-100"):
                if st.button("Buy", type="primary"):
                    if user.subscription.stripe_attempt_addon_purchase(amount):
                        raise RedirectException(payment_processing_url)
                    else:
                        st.error("Payment failed... Please try again.")
                if st.button("Cancel", className="border border-danger text-danger"):
                    confirm_purchase_modal.close()


def render_stripe_subscription_button(
    label: str,
    *,
    plan: PricingPlan,
    className: str = "streamlit-like-btn",
    type: str = "primary",
):
    if not plan.stripe:
        st.write("Stripe subscription not available")
        return

    btn_classes = f"btn btn-theme btn-{type} {className}"
    st.html(
        f"""
    <form action="{stripe_create_checkout_session_url}" method="post" class="d-inline">
        <input type="hidden" name="lookup_key" value="{plan.key}">
        <button type="submit" class="{btn_classes}" data-submit-disabled>{label}</button>
    </form>
    """
    )


def render_paypal_subscription_button(
    *,
    plan: PricingPlan,
):
    if not plan.paypal:
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
    with (
        col3,
        st.link(to=user.subscription.get_external_management_url(), target="_blank"),
    ):
        st.write(f"{icons.edit} Edit", unsafe_allow_html=True)

    pm_summary = user.subscription.get_payment_method_summary()
    if pm_summary and pm_summary.card_brand:
        col1, col2, col3 = st.columns(3, responsive=False)
        with col1:
            st.write("**Payment Method**")
        with col2:
            st.write(
                f"{format_card_brand(pm_summary.card_brand)} ending in {pm_summary.card_last4}",
                unsafe_allow_html=True,
            )
        with col3, st.link(to=change_payment_method_url):
            st.button(f"{icons.edit} Edit", type="link")

    if pm_summary and pm_summary.billing_email:
        col1, col2, _ = st.columns(3, responsive=False)
        with col1:
            st.write("**Billing Email**")
        with col2:
            st.html(pm_summary.billing_email)


def format_card_brand(brand: str) -> str:
    brand = brand.lower()
    if brand in icons.card_icons:
        return icons.card_icons[brand]
    else:
        return brand.capitalize()


def render_billing_history(user: AppUser):
    import pandas as pd

    txns = user.transactions.filter(amount__gt=0).order_by("-created_at")
    if not txns:
        return

    st.write("## Billing History", className="d-block")
    st.table(
        pd.DataFrame.from_records(
            columns=[""] * 3,
            data=[
                [
                    txn.created_at.strftime("%m/%d/%Y"),
                    txn.note(),
                    f"${txn.charged_amount / 100:,.2f}",
                ]
                for txn in txns
            ],
        )
    )


def render_auto_recharge_section(user: AppUser):
    assert (
        user.subscription
        and user.subscription.payment_provider == PaymentProvider.STRIPE
    )
    subscription = user.subscription

    st.write("## Auto Recharge & Limits")
    with st.div(className="d-flex align-items-center"):
        auto_recharge_enabled = st.checkbox(
            "", value=subscription.auto_recharge_enabled
        )
        st.write("#### Enable auto recharge")

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

    save_button_key = "save-auto-recharge-settings"
    with col1:
        st.button(
            "Save", type="primary", className="d-none d-lg-block", key=save_button_key
        )
    st.button("Save", type="primary", className="d-lg-none", key=save_button_key)

    if st.session_state.get(save_button_key):
        try:
            subscription.full_clean()
        except ValidationError as e:
            st.error(str(e))
            return

        with transaction.atomic():
            subscription.save()
        st.success("Settings saved!")


def border_box(*, className: str = "", **kwargs):
    className = className + " border shadow-sm rounded"
    return st.div(
        className=className,
        **kwargs,
    )


def left_and_right(**kwargs):
    className = kwargs.pop("className", "") + " d-flex flex-row justify-content-between"
    with st.div(className=className, **kwargs):
        return st.div(), st.div()
