import stripe
from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger

from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import fastapi_request_body
from payments.webhooks import StripeWebhookHandler
from routers.custom_api_router import CustomAPIRouter
from workspaces.models import Workspace

router = CustomAPIRouter()


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
    workspace = None
    try:
        workspace_id = customer.metadata["workspace_id"]
    except KeyError:
        pass
    else:
        workspace = Workspace.objects.get(id=workspace_id)
    try:
        uid = customer.metadata["uid"]
    except KeyError:
        pass
    else:
        workspace = Workspace.objects.get_or_create_from_uid(uid)[0]

    if not workspace:
        return JSONResponse(
            {
                "status": "failed",
                "error": "customer workspace / user  not found",
            },
            status_code=400,
        )

    logger.info(f"Received event: {event['type']}")

    # Get the type of webhook event sent - used to check the status of PaymentIntents.
    match event["type"]:
        case "invoice.paid":
            StripeWebhookHandler.handle_invoice_paid(workspace, data)
        case "invoice.payment_failed":
            StripeWebhookHandler.handle_invoice_failed(workspace, data)
        case "checkout.session.completed":
            StripeWebhookHandler.handle_checkout_session_completed(data)
        case "customer.subscription.created" | "customer.subscription.updated":
            StripeWebhookHandler.handle_subscription_updated(workspace, data)
        case "customer.subscription.deleted":
            StripeWebhookHandler.handle_subscription_cancelled(workspace)

    return JSONResponse({"status": "success"})
