import stripe
from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from firebase_admin.auth import UserRecord
from furl import furl

from daras_ai_v2 import db
from daras_ai_v2 import settings

STRIPE_CUSTOMER_ID_FIELD = "stripe_customer_id"

router = APIRouter(tags=["credits"])

stripe.api_key = settings.STRIPE_SECRET_KEY
templates = Jinja2Templates(directory="templates")

available_subscriptions = {
    "basic": {
        "price": {
            "price_data": {
                "currency": "usd",
                "product": settings.STRIPE_PRODUCT_ID,
                "unit_amount": 1,  # in cents
                "recurring": {
                    "interval": "month",
                },
            },
            "quantity": 1000,  # number of credits
        },
        "display": {
            "name": "Basic Plan",
            "title": "MONTHLY @ $10",
            "description": "1000 Credits to get you up, up and away. Cancel your plan anytime.",
        },
    },
    "premium": {
        "price": {
            "price_data": {
                "currency": "usd",
                "product": settings.STRIPE_PRODUCT_ID,
                "unit_amount": 1,  # in cents
                "recurring": {
                    "interval": "month",
                },
            },
            "quantity": 5000,  # number of credits
        },
        "display": {
            "name": "Premium Plan",
            "title": "MONTHLY @ $50",
            "description": "5000 Credits + special access to make bespoke interactive video bots! ",
        },
    },
    "addon": {
        "price": {
            "price_data": {
                "currency": "usd",
                "product": settings.STRIPE_PRODUCT_ID,
                "unit_amount": 1,  # in cents
            },
            "quantity": 1000,  # number of credits
            "adjustable_quantity": {
                "enabled": True,
                "maximum": 10_000,
                "minimum": 1_000,
            },
        },
        "display": {
            "name": "Premium Plan",
            "title": "Add-on",
            "description": "Pay an additional $10 to get 1000 extra credits on any monthly plan.",
        },
    },
}


@router.route("/__/stripe/create-checkout-session", methods=["POST"])
async def create_checkout_session(request: Request):
    user: UserRecord = request.user

    user_data_ref = db.get_user_doc_ref(user.uid)
    user_data = user_data_ref.get()

    form = await request.form()
    lookup_key = form["lookup_key"]

    if lookup_key == user_data.get("lookup_key"):
        # already subscribed
        return RedirectResponse("/", status_code=303)

    customer_id = user_data.get(STRIPE_CUSTOMER_ID_FIELD)
    if not customer_id:
        customer = stripe.Customer.create(
            name=user.display_name,
            email=user.email,
            phone=user.phone_number,
        )
        customer_id = customer.id
        user_data_ref.update({STRIPE_CUSTOMER_ID_FIELD: customer_id})

    price = available_subscriptions[lookup_key]["price"]

    try:
        price["price_data"]["recurring"]
    except KeyError:
        mode = "payment"
    else:
        mode = "subscription"

    checkout_session = stripe.checkout.Session.create(
        line_items=[price],
        mode=mode,
        success_url=str(furl(settings.APP_BASE_URL) / "payment-success"),
        cancel_url=str(furl(settings.APP_BASE_URL) / "payment-cancel"),
        client_reference_id=user.uid,
        metadata={
            "subscription": lookup_key,
        },
        customer=customer_id,
    )

    return RedirectResponse(checkout_session.url, status_code=303)


@router.route("/payment-cancel")
def payment_cancel(request):
    context = {"request": request}
    return templates.TemplateResponse("payment_cancel.html", context)


@router.route("/payment-success")
def payment_success(request):
    context = {"request": request}
    return templates.TemplateResponse("payment_success.html", context)


@router.route("/create-portal-session", methods=["POST"])
async def customer_portal(request: Request):
    user = request.user
    stripe_customer_id = db.get_user_field(user.uid, STRIPE_CUSTOMER_ID_FIELD)
    return_url = str(furl(settings.APP_BASE_URL) / "payment-success")
    portal_configuration = stripe.billing_portal.Configuration.create(
        features={
            "customer_update": {
                "enabled": False,
            },
            "invoice_history": {"enabled": True},
            "subscription_cancel": {"enabled": False},
        },
        business_profile={
            "privacy_policy_url": "https://dara.network/privacy/",
            "terms_of_service_url": "https://dara.network/terms/",
        },
    )
    portal_session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=return_url,
        configuration=portal_configuration.id,
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

    # Get the type of webhook event sent - used to check the status of PaymentIntents.
    event_type = event["type"]

    if event_type == "checkout.session.completed":
        _handle_checkout_session_completed(event)

    return JSONResponse({"status": "success"})


def _handle_checkout_session_completed(event):
    data = event["data"]["object"]

    checkout_id = data["id"]

    uid = data["client_reference_id"]
    assert uid, "client_reference_id not found"

    line_items = stripe.checkout.Session.list_line_items(checkout_id)
    quantity = line_items.data[0].quantity
    db.update_user_credits(uid, quantity, checkout_id)

    if data["mode"] == "subscription":
        subscription = data["metadata"]["subscription"]
        assert subscription, "subscription metadata not found"
        db.get_user_doc_ref(uid).update({"subscription": subscription})


@router.route("/cancel-subscription")
def cancel_subscription(request: Request):
    user = request.user
    customer_id = db.get_user_field(user.uid, STRIPE_CUSTOMER_ID_FIELD)
    subscriptions = stripe.Subscription.list(customer=customer_id)
    subscription_id = subscriptions["data"][0]["id"]
    stripe.Subscription.delete(subscription_id)
    db.get_user_doc_ref(user.uid).update({"lookup_key": None})
    return RedirectResponse("/account", status_code=303)
