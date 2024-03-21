import html
import os
import typing
from enum import Enum
from urllib.parse import quote_plus

import stripe
from fastapi import APIRouter, Depends, HTTPException
from fastapi.requests import Request
from fastapi.responses import RedirectResponse, JSONResponse
from furl import furl
from starlette.datastructures import FormData

import gooey_ui as st
from app_users.models import AppUser, PaymentProvider
from daras_ai_v2 import settings
from daras_ai_v2.base import RedirectException
from daras_ai_v2.manage_api_keys_widget import manage_api_keys
from daras_ai_v2.meta_content import raw_build_meta_tags
from daras_ai_v2.settings import templates
from routers.root import page_wrapper, request_json

USER_SUBSCRIPTION_METADATA_FIELD = "subscription_key"

router = APIRouter()

available_subscriptions = {
    "addon": {
        "display": {
            "name": "Add-on",
            "title": "Top up Credits",
        },
        "stripe": {
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Gooey.AI Add-on Credits",
                },
                "unit_amount": 1,  # in cents
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


class _AccountTab(typing.NamedTuple):
    title: str
    tab_path: str


class AccountTabs(Enum):
    billing = _AccountTab(title="Billing", tab_path="")
    profile = _AccountTab(title="Profile", tab_path="profile")
    api_keys = _AccountTab(title="🚀 API Keys", tab_path="api-keys")

    @property
    def title(self) -> str:
        return self.value.title

    @property
    def tab_path(self) -> str:
        return self.value.tab_path

    @classmethod
    def from_tab_path(cls, tab_path: str) -> "AccountTabs":
        for tab in cls:
            if tab.tab_path == tab_path:
                return tab
        raise HTTPException(status_code=404)

    def get_full_path(self) -> str:
        return os.path.join("/account", self.tab_path, "")


@router.post("/account/", include_in_schema=False)
@router.post("/account/{tab_path}/", include_in_schema=False)
def account(
    request: Request, tab_path: str = "", json_data: dict = Depends(request_json)
):
    tab = AccountTabs.from_tab_path(tab_path)
    try:
        ret = st.runner(
            lambda: page_wrapper(
                request,
                render_fn=lambda: render_account_page(request, tab),
            ),
            query_params=dict(request.query_params),
            **json_data,
        )
    except RedirectException as e:
        return RedirectResponse(e.url, status_code=e.status_code)
    else:
        ret |= {
            "meta": raw_build_meta_tags(
                url=account_url,
                title="Account • Gooey.AI",
                description="Your API keys, profile, and billing details.",
                canonical_url=account_url,
                robots="noindex,nofollow",
            )
        }
        return ret


def render_account_page(request: Request, current_tab: AccountTabs):
    if not request.user or request.user.is_anonymous:
        next_url = request.query_params.get("next", "/account/")
        redirect_url = furl("/login", query_params={"next": next_url})
        raise RedirectException(str(redirect_url))

    st.div(className="mt-5")
    with st.nav_tabs():
        for tab in AccountTabs:
            with st.nav_item(tab.get_full_path(), active=tab == current_tab):
                st.html(tab.title)

    with st.nav_tab_content():
        render_selected_tab(request, current_tab)


def render_selected_tab(request: Request, current_tab: AccountTabs):
    match current_tab:
        case AccountTabs.billing:
            billing_tab(request)
        case AccountTabs.profile:
            profile_tab(request)
        case AccountTabs.api_keys:
            api_keys_tab(request)
        case _:
            raise HTTPException(status_code=401)


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


def profile_tab(request: Request):
    with st.div(className="user-info"):
        if request.user and request.user.photo_url:
            st.html(
                f"""
            <img id="profile-picture" src="{html.escape(request.user.photo_url)}" alt="" width="128" height="128">
            """
            )
        with st.div(className="user-info-text-box"):
            if request.user.display_name:
                st.write(f"## {request.user.display_name}")
            if contact := request.user.email or request.user.phone_number:
                with st.div(style={"font-weight": "normal"}):
                    st.html(html.escape(contact))
            with st.div(
                className="mb-4",
                style={"font-size": "x-small", "font-weight": "normal"},
            ):
                st.html(
                    """<a href="/privacy">Privacy</a> & <a href="/terms">Terms</a>"""
                )
            with st.link(to="/logout"):
                st.caption("Sign out")


def api_keys_tab(request: Request):
    st.write("# 🔐 API Keys")
    manage_api_keys(request.user)


async def request_form(request: Request):
    return await request.form()


@router.post("/__/stripe/create-checkout-session")
def create_checkout_session(
    request: Request, body_form: FormData = Depends(request_form)
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


@router.post("/__/stripe/create-portal-session")
def customer_portal(request: Request):
    customer = request.user.get_or_create_stripe_customer()
    portal_session = stripe.billing_portal.Session.create(
        customer=customer,
        return_url=account_url,
    )
    return RedirectResponse(portal_session.url, status_code=303)


@router.get("/payment-success/")
def payment_success(request: Request):
    context = {"request": request, "settings": settings}
    return templates.TemplateResponse("payment_success.html", context)


payment_success_url = str(
    furl(settings.APP_BASE_URL) / router.url_path_for(payment_success.__name__)
)
account_url = str(furl(settings.APP_BASE_URL) / router.url_path_for(account.__name__))


async def request_body(request: Request):
    return await request.body()


@router.post("/__/stripe/webhook")
def webhook_received(request: Request, payload: bytes = Depends(request_body)):
    # Retrieve the event by verifying the signature using the raw body and secret if webhook signing is configured.
    event = stripe.Webhook.construct_event(
        payload=payload,
        sig_header=request.headers["stripe-signature"],
        secret=settings.STRIPE_ENDPOINT_SECRET,
    )

    data = event.data.object

    customer = stripe.Customer.retrieve(data.customer)
    try:
        uid = customer.metadata.uid
    except AttributeError:
        uid = None
    if not uid:
        return JSONResponse(
            {
                "status": "failed",
                "error": f"customer.metadata.uid not found",
            },
            status_code=400,
        )

    # Get the type of webhook event sent - used to check the status of PaymentIntents.
    match event["type"]:
        case "invoice.paid":
            _handle_invoice_paid(uid, data)

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


@router.post("/__/stripe/cancel-subscription")
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
