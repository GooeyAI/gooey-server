import stripe
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger

from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import fastapi_request_body
from payments.webhooks import StripeWebhookHandler

router = APIRouter()


@router.post("/__/stripe/webhook")
def webhook_received(request: Request, payload: bytes = fastapi_request_body):
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
                "error": "customer.metadata.uid not found",
            },
            status_code=400,
        )

    logger.info(f"Received event: {event['type']}")

    # Get the type of webhook event sent - used to check the status of PaymentIntents.
    match event["type"]:
        case "invoice.paid":
            StripeWebhookHandler.handle_invoice_paid(uid, data)
        case "checkout.session.completed":
            StripeWebhookHandler.handle_checkout_session_completed(uid, data)
        case "customer.subscription.created" | "customer.subscription.updated":
            StripeWebhookHandler.handle_subscription_updated(uid, data)
        case "customer.subscription.deleted":
            StripeWebhookHandler.handle_subscription_cancelled(uid, data)

    return JSONResponse({"status": "success"})
