import os
import typing
from contextlib import contextmanager
from enum import Enum
from textwrap import dedent

from urllib.parse import quote_plus

import stripe
from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import RedirectResponse, JSONResponse
from furl import furl
from starlette.datastructures import FormData

import gooey_ui as st
from app_users.models import AppUser, PaymentProvider
from bots.models import PublishedRun, PublishedRunVisibility, Workflow
from daras_ai_v2 import icons, settings, urls
from daras_ai_v2.auto_recharge import get_default_payment_method
from daras_ai_v2.base import RedirectException
from daras_ai_v2.fastapi_tricks import fastapi_request_body, fastapi_request_form
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.manage_api_keys_widget import manage_api_keys
from daras_ai_v2.meta_content import raw_build_meta_tags
from daras_ai_v2.profiles import edit_user_profile_page
from daras_ai_v2.settings import templates
from gooey_ui.components.pills import pill
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
            "quantity": 1500,  # number of credits
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
            "quantity": 10000,  # number of credits
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


def billing_tab(request: Request):
    if not request.user or request.user.is_anonymous:
        next_url = request.query_params.get("next", "/account/")
        redirect_url = furl("/login", query_params={"next": next_url})
        return RedirectResponse(str(redirect_url))

    is_admin = request.user.email in settings.ADMIN_EMAILS

    context = {
        "request": request,
        "settings": settings,
        "available_subscriptions": available_subscriptions,
        "user_credits": request.user.balance,
        "subscription": get_user_subscription(request.user),
        "is_admin": is_admin,
    }

    st.html(templates.get_template("account.html").render(**context))
    auto_recharge_section(request)


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


def auto_recharge_section(request: Request):
    assert request.user

    st.write("## Auto Recharge & Limits")
    col1, col2 = st.columns(2)

    with col1:
        with st.div(className="d-flex align-items-end"):
            auto_recharge_enabled = st.checkbox(
                "",
                value=request.user.auto_recharge_enabled,
            )
            st.write("#### Enable Auto Recharge")
        if not auto_recharge_enabled:
            st.caption(
                "Enable auto recharge to automatically keep your credit balance topped up."
            )

    if auto_recharge_enabled != request.user.auto_recharge_enabled:
        request.user.auto_recharge_enabled = auto_recharge_enabled
        request.user.save(update_fields=["auto_recharge_enabled"])
        st.experimental_rerun()

    if not request.user.auto_recharge_enabled:
        return

    pm = get_default_payment_method(request.user)
    if not pm:
        setup_default_payment_method_url = urls.remove_hostname(
            request.url_for("stripe_setup_default_payment_method")
        )
        st.write(
            f"Link a payment method with Stripe [here]({setup_default_payment_method_url})."
        )
        return

    with col1:
        request.user.auto_recharge_amount = st.selectbox(
            "Automatically purchase",
            options=settings.ADDON_AMOUNT_CHOICES,
            format_func=lambda amt: f"{settings.ADDON_CREDITS_PER_DOLLAR * amt:,} credits for ${amt}",
            default_value=request.user.auto_recharge_amount or 10,
        )
        request.user.auto_recharge_topup_threshold = st.selectbox(
            "When balance falls below (in credits)",
            options=[300, 1000, 3000, 10000],
            format_func=lambda credits: f"{credits:,} credits",
            default_value=request.user.auto_recharge_topup_threshold or 300,
        )

    with col2:
        request.user.auto_recharge_monthly_budget = st.number_input(
            dedent(
                """\
                #### Monthly Budget (in USD)

                If your account exceeds this budget in a given calendar month
                (UTC), subsequent runs & API requests will be rejected.
                """,
            ),
            min_value=10,
            value=request.user.auto_recharge_monthly_budget or 50,
        )
        request.user.auto_recharge_email_threshold = st.number_input(
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
            value=request.user.auto_recharge_email_threshold or 10,
        )

    st.write(
        f"Will automatically charge from {pm.card.brand} ending in {pm.card.last4}. ({pm.id=})",
    )
    if st.button("Save", type="primary"):
        request.user.save(
            update_fields=[
                "auto_recharge_amount",
                "auto_recharge_topup_threshold",
                "auto_recharge_monthly_budget",
                "auto_recharge_email_threshold",
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
    lookup_key = body_form["lookup_key"]
    subscription = available_subscriptions[lookup_key]
    line_item = subscription["stripe"].copy()

    quantity = body_form.get("quantity")
    if quantity:
        line_item["quantity"] = int(quantity)

    if get_user_subscription(request.user) == subscription:
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
    )

    return RedirectResponse(checkout_session.url, status_code=303)


@app.get("/__/stripe/setup-default-payment-method")
def stripe_setup_default_payment_method(request: Request):
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

    setup_intent = stripe.SetupIntent.retrieve(setup_intent_id)
    stripe.Customer.modify(
        session_data.customer,
        invoice_settings={"default_payment_method": setup_intent.payment_method},
    )


@app.post("/__/stripe/cancel-subscription")
def cancel_subscription(request: Request):
    customer = request.user.get_or_create_stripe_customer()
    subscriptions = stripe.Subscription.list(customer=customer).data
    for sub in subscriptions:
        stripe.Subscription.delete(sub.id)
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
