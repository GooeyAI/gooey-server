from urllib.parse import quote_plus

import stripe
from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from firebase_admin.auth import UserRecord
from furl import furl

from daras_ai_v2 import db
from daras_ai_v2 import settings

USER_SUBSCRIPTION_METADATA_FIELD = "subscription_key"

router = APIRouter()
templates = Jinja2Templates(directory="templates")


available_subscriptions = {
    "basic": {
        "display": {
            "name": "Basic Plan",
            "title": "MONTHLY @ $10",
            "description": "1000 Credits to get you up, up and away. Cancel your plan anytime.",
        },
        "stripe": {
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Gooey.AI Basic Plan",
                },
                "unit_amount": 1,  # in cents
                "recurring": {
                    "interval": "month",
                },
            },
            "quantity": 1000,  # number of credits
        },
    },
    "premium": {
        "display": {
            "name": "Premium Plan",
            "title": "MONTHLY @ $50",
            "description": "5000 Credits + special access to make bespoke interactive video bots! ",
        },
        "stripe": {
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Gooey.AI Premium Plan",
                },
                "unit_amount": 1,  # in cents
                "recurring": {
                    "interval": "month",
                },
            },
            "quantity": 5000,  # number of credits
        },
    },
    "addon": {
        "display": {
            "name": "Add-on",
            "title": "Add-on",
            "description": "Pay an additional $10 to get 1000 extra credits on any monthly plan.",
        },
        "stripe": {
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Gooey.AI Add-on Credits",
                },
                "unit_amount": 1,  # in cents
            },
            "quantity": 1000,  # number of credits
            "adjustable_quantity": {
                "enabled": True,
                "maximum": 10_000,
                "minimum": 1_000,
            },
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


@router.route("/account", include_in_schema=False)
def account(request: Request):
    if not request.user:
        next_url = request.query_params.get("next", "/account")
        redirect_url = furl("/login", query_params={"next": next_url})
        return RedirectResponse(str(redirect_url))

    user_data = db.get_or_init_user_data(request)

    context = {
        "request": request,
        "available_subscriptions": available_subscriptions,
        "user_credits": user_data.get(db.USER_BALANCE_FIELD, 0),
        "subscription": get_user_subscription(request.user),
    }

    return templates.TemplateResponse("account.html", context)


@router.route("/__/stripe/create-checkout-session", methods=["POST"])
async def create_checkout_session(request: Request):
    form = await request.form()
    lookup_key = form["lookup_key"]
    subscription = available_subscriptions[lookup_key]
    line_item = subscription["stripe"]

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
        success_url=str(furl(settings.APP_BASE_URL) / "payment-success"),
        cancel_url=str(furl(settings.APP_BASE_URL) / "payment-cancel"),
        customer=get_or_create_stripe_customer(request.user),
        metadata=metadata,
        subscription_data=subscription_data,
        invoice_creation=invoice_creation,
        allow_promotion_codes=True,
    )

    return RedirectResponse(checkout_session.url, status_code=303)


@router.route("/payment-success")
def payment_success(request):
    context = {"request": request}
    return templates.TemplateResponse("payment_success.html", context)


@router.route("/payment-cancel")
def payment_cancel(request):
    context = {"request": request}
    return templates.TemplateResponse("payment_cancel.html", context)


@router.route("/__/stripe/create-portal-session", methods=["POST"])
async def customer_portal(request: Request):
    customer = get_or_create_stripe_customer(request.user)
    portal_session = stripe.billing_portal.Session.create(
        customer=customer,
        return_url=str(furl(settings.APP_BASE_URL) / "account"),
    )
    return RedirectResponse(portal_session.url, status_code=303)


@router.route("/__/stripe/webhook", methods=["POST"])
async def webhook_received(request: Request):
    request_data = await request.body()

    # Retrieve the event by verifying the signature using the raw body and secret if webhook signing is configured.
    event = stripe.Webhook.construct_event(
        payload=request_data,
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
    amount = line_items.data[0].quantity
    db.update_user_balance(uid, amount, invoice_id)


@router.route("/__/stripe/cancel-subscription", methods=["POST"])
def cancel_subscription(request: Request):
    customer = get_or_create_stripe_customer(request.user)
    subscriptions = stripe.Subscription.list(customer=customer).data
    for sub in subscriptions:
        stripe.Subscription.delete(sub.id)
    return RedirectResponse("/account", status_code=303)


def get_user_subscription(user: UserRecord):
    customer = get_or_create_stripe_customer(user)
    subscriptions = stripe.Subscription.list(customer=customer).data
    for sub in subscriptions:
        try:
            lookup_key = sub.metadata[USER_SUBSCRIPTION_METADATA_FIELD]
            return available_subscriptions[lookup_key]
        except KeyError:
            pass


def get_or_create_stripe_customer(user: UserRecord):
    try:
        return stripe.Customer.search(query=f'metadata["uid"]:"{user.uid}"').data[0]
    except IndexError:
        return stripe.Customer.create(
            name=user.display_name,
            email=user.email,
            phone=user.phone_number,
            metadata={"uid": user.uid},
        )
