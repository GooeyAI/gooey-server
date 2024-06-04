from urllib.parse import quote_plus

import stripe
from django.db import transaction
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from loguru import logger

from app_users.models import AppUser
from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import (
    fastapi_request_body,
    get_route_url,
)
from payments.models import PaymentProvider, Subscription
from payments.plans import PricingPlan
from routers.account import (
    send_monthly_spending_notification_email,
    account_route,
)

router = APIRouter()


@router.post("/__/stripe/create-portal-session")
def customer_portal(request: Request):
    customer = request.user.get_or_create_stripe_customer()
    portal_session = stripe.billing_portal.Session.create(
        customer=customer,
        return_url=get_route_url(account_route),
    )
    return RedirectResponse(portal_session.url, status_code=303)


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
    if (
        user.subscription
        and user.subscription.should_send_monthly_spending_notification()
    ):
        send_monthly_spending_notification_email(user)


def _handle_checkout_session_completed(uid: str, session_data):
    setup_intent_id = session_data.get("setup_intent")
    if not setup_intent_id:
        # not a setup mode checkout
        return

    # set default payment method
    user = AppUser.objects.get_or_create_from_uid(uid)[0]
    setup_intent = stripe.SetupIntent.retrieve(setup_intent_id)
    subscription_id = setup_intent.metadata.get("subscription_id")
    if not (
        user.subscription.payment_provider == PaymentProvider.STRIPE
        and user.subscription.external_id == subscription_id
    ):
        logger.error(f"Subscription {subscription_id} not found for user {user}")
        return

    stripe.Subscription.modify(
        subscription_id, default_payment_method=setup_intent.payment_method
    )


@transaction.atomic
def _handle_subscription_updated(uid: str, subscription_data):
    logger.info("Subscription updated")
    product = stripe.Product.retrieve(subscription_data.plan.product)
    plan = PricingPlan.get_by_stripe_product(product)
    if not plan:
        raise Exception(
            f"PricingPlan not found for product {subscription_data.plan.product}"
        )

    if subscription_data.get("status") != "active":
        logger.warning(f"Subscription {subscription_data.id} is not active")
        return

    user = AppUser.objects.get_or_create_from_uid(uid)[0]
    if user.subscription and (
        user.subscription.payment_provider != PaymentProvider.STRIPE
        or user.subscription.external_id != subscription_data.id
    ):
        logger.warning(
            f"User {user} has different existing subscription {user.subscription}. Cancelling that..."
        )
        user.subscription.cancel()
        user.subscription.delete()
    elif not user.subscription:
        user.subscription = Subscription()

    user.subscription.plan = plan.db_value
    user.subscription.payment_provider = PaymentProvider.STRIPE
    user.subscription.external_id = subscription_data.id

    user.subscription.full_clean()
    user.subscription.save()
    user.save(update_fields=["subscription"])


def _handle_subscription_cancelled(uid: str, subscription_data):
    subscription = Subscription.objects.get_by_stripe_subscription_id(
        subscription_data.id
    )
    logger.info(f"Subscription {subscription} cancelled. Deleting it...")
    subscription.delete()
