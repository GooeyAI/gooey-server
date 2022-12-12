from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from daras_ai import db
from daras_ai_v2.settings import STRIPE_SECRET_KEY, STRIPE_WEBHOOKS_KEY, APP_BASE_URL
import stripe

router = APIRouter(tags=["credits"])

stripe.api_key = STRIPE_SECRET_KEY
templates = Jinja2Templates(directory="templates")


@router.route("/create-checkout-session-add-on", methods=["POST"])
def create_checkout_session(request):
    user = request.user
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    "price": "price_1M2XyPBBJIwZF3wzw58VipNK",
                    "quantity": 1,
                },
            ],
            mode="payment",
            success_url=APP_BASE_URL + "/payment-success",
            cancel_url=APP_BASE_URL + "/payment-cancel",
            customer_email=user.email,
            client_reference_id=user.uid,
        )
    except Exception as e:
        return str(e)

    return RedirectResponse(checkout_session.url, status_code=303)


@router.route("/payment-cancel")
def payment_cancel(request):
    context = {"request": request}
    return templates.TemplateResponse("payment_cancel.html", context)


@router.route("/payment-success")
def payment_success(request):
    context = {"request": request}
    return templates.TemplateResponse("payment_success.html", context)


@router.route("/create-checkout-session", methods=["POST"])
async def create_checkout_session(request: Request):
    try:
        user = request.user
        form = await request.form()
        form_lookup_key = form["lookup_key"]
        lookup_key_from_db = db.get_user_field(user.uid, "lookup_key")
        if form_lookup_key == lookup_key_from_db:
            return RedirectResponse("/", status_code=303)
        prices = stripe.Price.list(
            lookup_keys=[form_lookup_key], expand=["data.product"]
        )
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    "price": prices.data[0].id,
                    "quantity": 1,
                },
            ],
            mode="subscription",
            success_url=APP_BASE_URL + "/payment-success",
            cancel_url=APP_BASE_URL + "/payment-cancel",
            customer_email=user.email,
            client_reference_id=user.uid,
        )
        return RedirectResponse(checkout_session.url, status_code=303)
    except Exception as e:
        print(e)
        return "Server error", 500


@router.route("/create-portal-session", methods=["POST"])
async def customer_portal(request: Request):
    user = request.user
    stripe_customer_id = db.get_user_field(user.uid, "stripe_customer_id")
    return_url = APP_BASE_URL + "/payment-success"
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


@router.route("/webhook", methods=["POST"])
async def webhook_received(request: Request):
    event = None
    webhook_secret = STRIPE_WEBHOOKS_KEY
    request_data = await request.body()

    if webhook_secret:
        # Retrieve the event by verifying the signature using the raw body and secret if webhook signing is configured.
        signature = request.headers.get("stripe-signature")
        try:
            event = stripe.Webhook.construct_event(
                payload=request_data, sig_header=signature, secret=webhook_secret
            )
            data = event["data"]
        except Exception as e:
            print(e)
            return
        # Get the type of webhook event sent - used to check the status of PaymentIntents.
        event_type = event["type"]
    else:
        data = request_data["data"]
        event_type = request_data["type"]
    data_object = data["object"]

    if event_type == "checkout.session.completed":
        subscription_id = data_object["subscription"]
        uid = data_object["client_reference_id"]
        if not subscription_id:
            db.add_user_credits(uid, 1000)
            return JSONResponse({"status": "success"})

        subscription = stripe.Subscription.retrieve(subscription_id)
        product_id = subscription["items"]["data"][0]["plan"]["product"]
        product = stripe.Product.retrieve(product_id)
        credits_to_add = int(product["metadata"]["credits"])
        db.add_user_credits(uid, credits_to_add)
        plan_lookup_key = subscription["items"]["data"][0]["price"]["lookup_key"]
        data_to_add_in_db = {
            "lookup_key": plan_lookup_key,
            "stripe_customer_id": data_object["customer"],
        }
        db.add_data_to_user_doc(uid, data_to_add_in_db)

    return JSONResponse({"status": "success"})


@router.route("/cancel-subscription")
def cancel_subscription(request: Request):
    user = request.user
    customer_id = db.get_user_field(user.uid, "stripe_customer_id")
    subscriptions = stripe.Subscription.list(customer=customer_id)
    subscription_id = subscriptions["data"][0]["id"]
    stripe.Subscription.delete(subscription_id)
    db.add_data_to_user_doc(user.uid, {"lookup_key": None})
    return RedirectResponse("/account", status_code=303)
