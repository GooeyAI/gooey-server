from functools import wraps
import os
import typing
from contextlib import contextmanager
from enum import Enum
from textwrap import dedent
from urllib.parse import quote_plus

import stripe
from django.db import transaction
from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import RedirectResponse, JSONResponse
from furl import furl
from loguru import logger
from starlette.datastructures import FormData

import gooey_ui as st
from app_users.models import AppUser, PaymentProvider
from bots.models import PublishedRun, PublishedRunVisibility, Workflow
from daras_ai_v2 import icons, settings, urls
from daras_ai_v2.auto_recharge import get_auto_recharge_payment_method
from daras_ai_v2.base import RedirectException
from daras_ai_v2.fastapi_tricks import fastapi_request_body, fastapi_request_form
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.manage_api_keys_widget import manage_api_keys
from daras_ai_v2.meta_content import raw_build_meta_tags
from daras_ai_v2.profiles import edit_user_profile_page
from daras_ai_v2.settings import templates
from gooey_ui.components.pills import pill
from payments.models import AutoRechargeSubscription, PricingPlan, Subscription
from routers.root import page_wrapper

USER_SUBSCRIPTION_METADATA_FIELD = "subscription_key"

app = APIRouter()

available_subscriptions = {
    "addon": {
        "display": {
            "name": "Add-on",
            "title": "Top up Credits",
            "description": f"Buy a one-time top up @ {settings.ADDON_CREDITS_PER_DOLLAR} Credits per dollar.",
        },
        "stripe": {
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Gooey.AI Add-on Credits",
                },
                "unit_amount_decimal": (
                    settings.ADDON_CREDITS_PER_DOLLAR / 100
                ),  # in cents
            },
            # "quantity": 1000,  # number of credits (set by html)
            "adjustable_quantity": {
                "enabled": True,
                "maximum": 50_000,
                "minimum": 1_000,
            },
        },
        "paypal": {
            "plan_id": settings.PAYPAL_PLAN_IDS["addon"],
        },
    },
    "basic": {
        "display": {
            "name": "Basic Plan",
            "title": "$10/Month",
            "description": "Buy a monthly plan for $10 and get new 1500 credits (~300 runs) every month.",
        },
        "stripe": {
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Gooey.AI Basic Plan",
                },
                "unit_amount_decimal": 0.6666,  # in cents
                "recurring": {
                    "interval": "month",
                },
            },
            "quantity": 1_500,  # number of credits
        },
        "paypal": {
            "plan_id": settings.PAYPAL_PLAN_IDS["basic"],
            "plan": {
                "billing_cycles": [
                    {
                        "pricing_scheme": {
                            "fixed_price": {
                                "value": 10,  # in dollars
                                "currency_code": "USD",
                            },
                        },
                        "sequence": 1,
                        "total_cycles": 0,
                    }
                ],
            },
            "quantity": 1_500,  # number of credits
        },
    },
    "premium": {
        "display": {
            "name": "Premium Plan",
            "title": "$50/month + Bots",
            "description": '10000 Credits (~2000 runs) for $50/month. Includes special access to build bespoke, embeddable <a href="/video-bots/">videobots</a>.',
        },
        "stripe": {
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Gooey.AI Premium Plan",
                },
                "unit_amount_decimal": 0.5,  # in cents
                "recurring": {
                    "interval": "month",
                },
            },
            "quantity": 10_000,  # number of credits
        },
        "paypal": {
            "plan_id": settings.PAYPAL_PLAN_IDS["premium"],
            "plan": {
                "billing_cycles": [
                    {
                        "pricing_scheme": {
                            "fixed_price": {
                                "value": 50,
                                "currency_code": "USD",
                            },
                        },
                        "sequence": 1,
                        "total_cycles": 0,
                    }
                ],
            },
            "quantity": 10_000,  # number of credits
        },
    },
    #
    # just for testing
    #
    # "daily": {
    #     "display": {
    #         "name": "Daily Plan",
    #         "title": "DAILY @ $1",
    #         "description": "100 credits everyday.",
    #     },
    #     "stripe": {
    #         "price_data": {
    #             "currency": "usd",
    #             "product_data": {
    #                 "name": "Gooey.AI Daily Plan",
    #             },
    #             "unit_amount": 1,  # in cents
    #             "recurring": {
    #                 "interval": "day",
    #             },
    #         },
    #         "quantity": 100,  # number of credits
    #     },
    # },
}


@app.post("/account/")
@st.route
def account_route(request: Request):
    with account_page_wrapper(request, AccountTabs.billing):
        billing_tab(request)
    return dict(
        meta=raw_build_meta_tags(
            url=str(request.url),
            title="Billing • Gooey.AI",
            description="Your billing details.",
            canonical_url=str(request.url),
            robots="noindex,nofollow",
        )
    )


@app.post("/account/profile/")
@st.route
def profile_route(request: Request):
    with account_page_wrapper(request, AccountTabs.profile):
        profile_tab(request)
    return dict(
        meta=raw_build_meta_tags(
            url=str(request.url),
            title="Profile • Gooey.AI",
            description="Your profile details.",
            canonical_url=str(request.url),
            robots="noindex,nofollow",
        )
    )


@app.post("/saved/")
@st.route
def saved_route(request: Request):
    with account_page_wrapper(request, AccountTabs.saved):
        all_saved_runs_tab(request)
    return dict(
        meta=raw_build_meta_tags(
            url=str(request.url),
            title="Saved • Gooey.AI",
            description="Your saved runs.",
            canonical_url=str(request.url),
            robots="noindex,nofollow",
        )
    )


@app.post("/account/api-keys/")
@st.route
def api_keys_route(request: Request):
    with account_page_wrapper(request, AccountTabs.api_keys):
        api_keys_tab(request)
    return dict(
        meta=raw_build_meta_tags(
            url=str(request.url),
            title="API Keys • Gooey.AI",
            description="Your API keys.",
            canonical_url=str(request.url),
            robots="noindex,nofollow",
        )
    )


class TabData(typing.NamedTuple):
    title: str
    route: typing.Callable


class AccountTabs(TabData, Enum):
    billing = TabData(title=f"{icons.billing} Billing", route=account_route)
    profile = TabData(title=f"{icons.profile} Profile", route=profile_route)
    saved = TabData(title=f"{icons.save} Saved", route=saved_route)
    api_keys = TabData(title=f"{icons.api} API Keys", route=api_keys_route)

    @property
    def url_path(self) -> str:
        return os.path.join(app.url_path_for(self.route.__name__), "")


def border_box(*, className: str = "", **kwargs):
    className = className + " border shadow-sm rounded"
    return st.div(
        className=className,
        **kwargs,
    )


def _accept_props_as_callable(component):
    @wraps(component)
    def wrapper(**kwargs):
        component.node.props.update(kwargs)
        return component

    return wrapper


def left_and_right(**kwargs):
    className = kwargs.pop("className", "") + " d-flex flex-row justify-content-between"
    with st.div(className=className, **kwargs):
        return _accept_props_as_callable(st.div()), _accept_props_as_callable(st.div())


def billing_tab(request: Request):
    if not request.user or request.user.is_anonymous:
        next_url = request.query_params.get("next", "/account/")
        redirect_url = furl("/login", query_params={"next": next_url})
        return RedirectResponse(str(redirect_url))

    render_payments_setup()

    if request.user.subscription:
        render_current_plan(request.user.subscription)

    with st.div(className="mt-4"):
        st.write(
            f"""\
# Remaining Credits: {request.user.balance:,}

Every time you submit a workflow or make an API call, we deduct credits from your account.
"""
        )

    render_all_plans(user=request.user)
    render_auto_recharge_section(request)
    render_addon_section()
    render_billing_history(request.user)

    return
    is_admin = request.user.email in settings.ADMIN_EMAILS

    context = {
        "request": request,
        "settings": settings,
        "available_subscriptions": available_subscriptions,
        "user_credits": request.user.balance,
        "is_admin": is_admin,
        "subscription": request.user.subscription,
        "subscription_plan": (
            PricingPlan(request.user.subscription.plan)
            if request.user.subscription
            else None
        ),
        "PaymentProvider": PaymentProvider,
    }

    st.html(templates.get_template("account.html").render(**context))
    render_auto_recharge_section(request)


def render_payments_setup():
    st.html(templates.get_template("payment_setup.html").render(settings=settings))


def render_current_plan(subscription: Subscription):
    plan = PricingPlan(subscription.plan)
    with border_box(className="w-100 p-3"):
        left, right = left_and_right(className="align-items-center")
        with left():
            st.write(
                dedent(
                    f"""
                #### Gooey.AI {plan.title}

                [{icons.edit} Manage Subscription](/__/stripe/create-portal-session)
                """
                ),
                unsafe_allow_html=True,
            )
        if plan.monthly_charge:
            with right(className="text-muted"), st.tag("p"):
                st.html("Next invoice on ")
                pill(
                    subscription.get_next_invoice_date().strftime("%b %d, %Y"),
                    type="dark",
                )

        left, right = left_and_right(className="mt-5")
        with left():
            with st.tag("h1", className="my-0"):
                st.html(plan.pricing_title())
            if plan.monthly_charge:
                st.caption("per month")
        with right(className="text-end"):
            with st.tag("h1", className="my-0"):
                st.html(f"{plan.credits:,} credits")
            if plan.monthly_charge:
                st.write(
                    f"**${plan.monthly_charge:,}** monthly renewal for {plan.credits:,} credits"
                )


def render_all_plans(user: AppUser):
    current_plan = (
        PricingPlan(user.subscription.plan)
        if user.subscription
        else PricingPlan.STARTER
    )

    all_plans = [plan for plan in PricingPlan if not plan.deprecated]

    def _render_plan(plan: PricingPlan):
        current_plan_class = "bg-light" if plan == current_plan else ""
        with border_box(
            className=f"p-3 {current_plan_class} h-100 d-flex justify-content-between flex-column"
        ):
            with st.div():
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

            btn_classes = "w-100 mt-3"
            if current_plan == plan:
                st.button(
                    "Your Plan", className=btn_classes, disabled=True, type="tertiary"
                )
            elif plan.contact_us_link:
                with st.link(to=plan.contact_us_link):
                    st.button("Contact Us", className=btn_classes, type="primary")
            else:
                action_text, btn_type = (
                    ("Upgrade", "primary")
                    if plan.credits > current_plan.credits
                    else ("Downgrade", "secondary")
                )
                key = f"__change-plan-{plan.key}"
                if st.button(
                    action_text, key=key, className=btn_classes, type=btn_type
                ):
                    # TODO: change user plan
                    ...

    st.write("## All Plans")
    grid_layout(4, all_plans, _render_plan, separator=False)


def payment_provider_radio():
    with st.div(className="d-flex"):
        st.write("###### Pay Via", className="d-block me-3")
        return st.radio(
            "",
            options=PaymentProvider.labels,
            format_func=lambda l: f'<span class="me-3">{l}</span>',
        )


def render_addon_section():
    st.write("# Purchase More Credits")
    st.caption(f"Buy more credits. $1 per {settings.ADDON_CREDITS_PER_DOLLAR} credits")

    provider = payment_provider_radio()
    match provider:
        case PaymentProvider.STRIPE.label:
            for amount in settings.ADDON_AMOUNT_CHOICES:
                render_stripe_addon_button(amount)
        case PaymentProvider.PAYPAL.label:
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
    >Buy ${amount}</button>
    """
    )


def render_stripe_addon_button(amount: int):
    st.html(
        f"""
    <form action="/__/stripe/create-checkout-session" method="post" class="d-inline">
        <input type="hidden" name="lookup_key" value="addon">
        <input type="hidden" name="quantity" value="{amount * settings.ADDON_CREDITS_PER_DOLLAR}">
        <button type="submit" class="streamlit-like-btn" data-submit-disabled>Buy ${amount}</button>
    </form>
    """
    )


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
    <form action="/__/stripe/create-checkout-session" method="post" class="d-inline">
        <input type="hidden" name="lookup_key" value="{plan.key}">
        <button type="submit" class="{btn_classes}" data-submit-disabled>{label}</button>
    </form>
    """
    )


def render_paypal_subscription_button(
    label: str,
    *,
    plan: PricingPlan,
    className: str = "streamlit-like-btn",
    type: str = "primary",
):
    if not plan.paypal or "plan_id" not in plan.paypal:
        st.write("Paypal subscription not available")
        return

    className += f" btn btn-theme btn-{type}"
    st.html(
        f"""
    <button class="paypal-subscription-buttons {className}"
            type="button"
            data-plan-id="{plan.paypal['plan_id']}"
            data-submit-disabled
    >{label}</button>
    """
    )


def render_billing_history(user: AppUser):
    import pandas as pd

    txns = user.transactions.filter(amount__gt=0).order_by("-created_at")

    st.write("## Billing History")
    if not txns:
        st.caption("No purchases yet")
    else:
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


def profile_tab(request: Request):
    return edit_user_profile_page(user=request.user)


def all_saved_runs_tab(request: Request):
    prs = PublishedRun.objects.filter(
        created_by=request.user,
    ).order_by("-updated_at")

    def _render_run(pr: PublishedRun):
        workflow = Workflow(pr.workflow)
        visibility = PublishedRunVisibility(pr.visibility)

        with st.div(className="mb-2 d-flex justify-content-between align-items-start"):
            pill(
                visibility.get_badge_html(),
                unsafe_allow_html=True,
                className="border border-dark",
            )
            pill(workflow.short_title, className="border border-dark")

        workflow.page_cls().render_published_run_preview(pr)

    st.write("# Saved Workflows")

    if prs:
        if request.user.handle:
            st.caption(
                "All your Saved workflows are here, with public ones listed on your "
                f"profile page at {request.user.handle.get_app_url()}."
            )
        else:
            edit_profile_url = AccountTabs.profile.url_path
            st.caption(
                "All your Saved workflows are here. Public ones will be listed on your "
                f"profile page if you [create a username]({edit_profile_url})."
            )

        with st.div(className="mt-4"):
            grid_layout(3, prs, _render_run)
    else:
        st.write("No saved runs yet", className="text-muted")


def api_keys_tab(request: Request):
    st.write("# 🔐 API Keys")
    manage_api_keys(request.user)


def render_auto_recharge_section(request: Request):
    assert request.user

    st.write("## Auto Recharge & Limits")
    col1, col2 = st.columns(2)

    with col1, st.div(className="d-flex align-items-end"):
        auto_recharge_enabled = st.checkbox("", value=bool(request.user.auto_recharge))
        st.write("#### Enable Auto Recharge")

    if not auto_recharge_enabled:
        if request.user.auto_recharge:
            with transaction.atomic():
                request.user.auto_recharge.delete()
                request.user.auto_recharge = None
                request.user.save(update_fields=["auto_recharge"])
            st.experimental_rerun()

        with col1:
            st.caption(
                "Enable auto recharge to automatically keep your credit balance topped up."
            )

        return

    if not request.user.auto_recharge:
        request.user.auto_recharge = AutoRechargeSubscription(
            topup_amount=settings.ADDON_AMOUNT_CHOICES[0],
            topup_threshold=settings.AUTO_RECHARGE_TOPUP_THRESHOLD_CHOICES[0],
        )
        with transaction.atomic():
            request.user.auto_recharge.save()
            request.user.save(update_fields=["auto_recharge"])
        st.experimental_rerun()

    setup_auto_recharge_url = urls.remove_hostname(
        request.url_for("stripe_setup_auto_recharge")
    )
    pm = get_auto_recharge_payment_method(request.user)
    if not pm:
        st.write(
            f"Link a payment method with Stripe [here]({setup_auto_recharge_url})."
        )
        return

    with col1:
        request.user.auto_recharge.topup_amount = st.selectbox(
            "Automatically purchase",
            options=settings.ADDON_AMOUNT_CHOICES,
            format_func=lambda amt: f"{settings.ADDON_CREDITS_PER_DOLLAR * amt:,} credits for ${amt}",
            default_value=request.user.auto_recharge.topup_amount,
        )
        request.user.auto_recharge.topup_threshold = st.selectbox(
            "When balance falls below (in credits)",
            options=settings.AUTO_RECHARGE_TOPUP_THRESHOLD_CHOICES,
            format_func=lambda credits: f"{credits:,} credits",
            default_value=request.user.auto_recharge.topup_threshold,
        )
        card_icon = f'<i class="fa-brands fa-cc-{pm.card.brand}"></i>'
        st.write(
            '<span class="text-muted">Using my card ending in </span>'
            f"**{pm.card.last4}** {card_icon}. "
            f'<span class="text-muted">[Change]({setup_auto_recharge_url})</span>',
            unsafe_allow_html=True,
        )

    with col2:
        request.user.monthly_spending_budget = st.number_input(
            dedent(
                """\
                #### Monthly Budget (in USD)

                If your account exceeds this budget in a given calendar month
                (UTC), subsequent runs & API requests will be rejected.
                """,
            ),
            min_value=10,
            value=request.user.monthly_spending_budget or 50,
        )
        request.user.monthly_spending_notification_threshold = st.number_input(
            dedent(
                """\
                #### Email Notification Threshold (in USD)

                If your account purchases exceed this threshold in a given
                calendar month (UTC), you will receive an email notification.
                This include both manual and auto-recharge purchases.
                """,
            ),
            min_value=10,
            max_value=10000,
            value=request.user.monthly_spending_notification_threshold or 10,
        )

    if st.button("Save", type="primary"):
        with transaction.atomic():
            request.user.auto_recharge.external_id = pm.id
            request.user.auto_recharge.payment_provider = PaymentProvider.STRIPE
            request.user.auto_recharge.save()
            request.user.save(
                update_fields=[
                    "auto_recharge",
                    "monthly_spending_budget",
                    "monthly_spending_notification_threshold",
                ]
            )
        st.success("Settings saved!")


async def request_form(request: Request):
    return await request.form()


@contextmanager
def account_page_wrapper(request: Request, current_tab: TabData):
    if not request.user or request.user.is_anonymous:
        next_url = request.query_params.get("next", "/account/")
        redirect_url = furl("/login", query_params={"next": next_url})
        raise RedirectException(str(redirect_url))

    with page_wrapper(request):
        st.div(className="mt-5")
        with st.nav_tabs():
            for tab in AccountTabs:
                with st.nav_item(tab.url_path, active=tab == current_tab):
                    st.html(tab.title)

        with st.nav_tab_content():
            yield


@app.post("/__/stripe/create-checkout-session")
def create_checkout_session(
    request: Request, body_form: FormData = fastapi_request_form
):
    if not request.user:
        return RedirectResponse(
            request.url_for("login", query_params={"next": request.url.path})
        )

    lookup_key: str = body_form["lookup_key"]
    if lookup_key == "addon":
        plan = available_subscriptions["addon"]
        line_item = available_subscriptions["addon"]["stripe"].copy()
    elif plan := PricingPlan.get_by_key(lookup_key):
        line_item = plan.stripe.copy()
    else:
        return JSONResponse(
            {
                "message": "Invalid plan lookup key",
            }
        )

    quantity = body_form.get("quantity")
    if quantity:
        line_item["quantity"] = int(quantity)

    if request.user.subscription and request.user.subscription.plan == plan.value:
        # already subscribed
        return RedirectResponse("/", status_code=303)

    metadata = {USER_SUBSCRIPTION_METADATA_FIELD: lookup_key}

    try:
        # check if recurring payment
        line_item["price_data"]["recurring"]
    except KeyError:
        mode = "payment"
        invoice_creation = {"enabled": True}
        subscription_data = None  # can't pass subscription_data in payment mode
    else:
        mode = "subscription"
        invoice_creation = None  # invoice automatically genearated in subscription mode
        subscription_data = {"metadata": metadata}

    checkout_session = stripe.checkout.Session.create(
        line_items=[line_item],
        mode=mode,
        success_url=payment_success_url,
        cancel_url=account_url,
        customer=request.user.get_or_create_stripe_customer(),
        metadata=metadata,
        subscription_data=subscription_data,
        invoice_creation=invoice_creation,
        allow_promotion_codes=True,
        # saved_payment_method_options={
        #     "payment_method_save": "enabled",
        # },
    )

    return RedirectResponse(checkout_session.url, status_code=303)


@app.get("/__/stripe/setup-auto-recharge")
def stripe_setup_auto_recharge(request: Request):
    if not request.user or request.user.is_anonymous:
        return RedirectResponse(
            request.url_for("login", query_params={"next": request.url.path})
        )

    checkout_session = stripe.checkout.Session.create(
        mode="setup",
        currency="usd",
        customer=request.user.get_or_create_stripe_customer(),
        success_url=payment_success_url,
        cancel_url=account_url,
    )

    return RedirectResponse(checkout_session.url, status_code=303)


@app.post("/__/stripe/create-portal-session")
def customer_portal(request: Request):
    customer = request.user.get_or_create_stripe_customer()
    portal_session = stripe.billing_portal.Session.create(
        customer=customer,
        return_url=account_url,
    )
    return RedirectResponse(portal_session.url, status_code=303)


@app.get("/payment-success/")
def payment_success(request: Request):
    context = {"request": request, "settings": settings}
    return templates.TemplateResponse("payment_success.html", context)


payment_success_url = str(
    furl(settings.APP_BASE_URL) / app.url_path_for(payment_success.__name__)
)
account_url = str(
    furl(settings.APP_BASE_URL) / app.url_path_for(account_route.__name__)
)


@app.post("/__/stripe/webhook")
def webhook_received(request: Request, payload: bytes = fastapi_request_body):
    # Retrieve the event by verifying the signature using the raw body and secret if webhook signing is configured.
    event = stripe.Webhook.construct_event(
        payload=payload,
        sig_header=request.headers["stripe-signature"],
        secret=settings.STRIPE_ENDPOINT_SECRET,
    )

    data = event.data.object

    try:
        customer = stripe.Customer.retrieve(data.customer)
        uid = customer.metadata.uid
    except AttributeError:
        uid = None
    if not uid:
        return JSONResponse(
            {
                "status": "failed",
                "error": "customer.metadata.uid not found",
            },
            status_code=400,
        )

    # Get the type of webhook event sent - used to check the status of PaymentIntents.
    match event["type"]:
        case "invoice.paid":
            _handle_invoice_paid(uid, data)
        case "checkout.session.completed":
            _handle_checkout_session_completed(uid, data)
        case "customer.subscription.created" | "customer.subscription.updated":
            _handle_subscription_updated(uid, data)
        case "customer.subscription.deleted":
            _handle_subscription_cancelled(uid, data)

    return JSONResponse({"status": "success"})


def _handle_invoice_paid(uid: str, invoice_data):
    invoice_id = invoice_data.id
    line_items = stripe.Invoice._static_request(
        "get",
        "/v1/invoices/{invoice}/lines".format(invoice=quote_plus(invoice_id)),
    )
    user = AppUser.objects.get_or_create_from_uid(uid)[0]
    user.add_balance(
        payment_provider=PaymentProvider.STRIPE,
        invoice_id=invoice_id,
        amount=line_items.data[0].quantity,
        charged_amount=line_items.data[0].amount,
    )
    if not user.is_paying:
        user.is_paying = True
        user.save(update_fields=["is_paying"])


def _handle_checkout_session_completed(uid: str, session_data):
    setup_intent_id = session_data.get("setup_intent")
    if not setup_intent_id:
        # not a setup mode checkout
        return

    user = AppUser.objects.get_or_create_from_uid(uid)[0]
    if not user.auto_recharge:
        logger.error("AutoRechargeSubscription not found for user %s", user)
        return

    setup_intent = stripe.SetupIntent.retrieve(setup_intent_id)
    user.auto_recharge.payment_provider = PaymentProvider.STRIPE
    user.auto_recharge.external_id = setup_intent.payment_method
    user.auto_recharge.save(update_fields=["payment_provider", "external_id"])


@transaction.atomic
def _handle_subscription_updated(uid: str, subscription_data):
    logger.info(f"Subscription updated: {subscription_data}")

    if subscription_data.get("status") != "active":
        return

    product = stripe.Product.retrieve(subscription_data.plan.product)
    plan = PricingPlan.get_by_stripe_product_name(product.name)
    if not plan:
        raise Exception(
            f"PricingPlan not found for product {subscription_data.plan.product}"
        )

    user = AppUser.objects.get_or_create_from_uid(uid)[0]
    if (
        user.subscription
        and user.subscription.payment_provider == PaymentProvider.STRIPE
        and user.subscription.external_id == subscription_data.id
    ):
        # this subscription already exists
        return
    elif user.subscription:
        logger.warning(
            f"User {user} has existing subscription {user.subscription}. Cancelling that..."
        )
        user.subscription.cancel()

    user.subscription = Subscription(
        plan=plan.value,
        payment_provider=PaymentProvider.STRIPE,
        external_id=subscription_data.id,
    )
    user.subscription.save()
    user.save(update_fields=["subscription"])


def _handle_subscription_cancelled(uid: str, subscription_data):
    user = AppUser.objects.get_or_create_from_uid(uid)[0]
    if (
        user.subscription
        and user.subscription.payment_provider == PaymentProvider.STRIPE
        and user.subscription.external_id == subscription_data.id
    ):
        user.subscription = None
        user.save(update_fields=["subscription"])


@app.post("/__/stripe/cancel-subscription")
def cancel_stripe_subscription(request: Request):
    customer = request.user.get_or_create_stripe_customer()
    subscriptions = stripe.Subscription.list(customer=customer).data
    for sub in subscriptions:
        stripe.Subscription.delete(sub.id)
    return RedirectResponse("/account/", status_code=303)


@app.post("/__/cancel-subscription")
def cancel_subscription(request: Request):
    user = request.user
    if not user.subscription:
        return RedirectResponse("/account/", status_code=303)

    user.subscription.cancel()
    user.subscription.delete()
    return RedirectResponse("/account/", status_code=303)


def get_user_subscription(user: AppUser):
    customer = user.search_stripe_customer()
    if not customer:
        return
    subscriptions = stripe.Subscription.list(customer=customer).data
    for sub in subscriptions:
        try:
            lookup_key = sub.metadata[USER_SUBSCRIPTION_METADATA_FIELD]
            return available_subscriptions[lookup_key]
        except KeyError:
            pass
