from urllib.parse import quote_plus

import stripe
from django.db import transaction
from fastapi.datastructures import FormData
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi import APIRouter, Request
from loguru import logger

from app_users.models import AppUser
from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import fastapi_request_body, fastapi_request_form
from payments.models import PaymentProvider, Subscription
from payments.plans import PricingPlan
from routers.billing import (
    send_monthly_spending_notification_email,
    account_url,
    payment_processing_url,
)

router = APIRouter()


@router.post("/__/stripe/create-checkout-session")
def create_checkout_session(
    request: Request, body_form: FormData = fastapi_request_form
):
    if not request.user:
        return RedirectResponse(
            request.url_for("login", query_params={"next": request.url.path})
        )

    lookup_key: str = body_form["lookup_key"]
    if plan := PricingPlan.get_by_key(lookup_key):
        line_item = plan.get_stripe_line_item()
    else:
        return JSONResponse(
            {
                "message": "Invalid plan lookup key",
            }
        )

    if request.user.subscription and request.user.subscription.plan == plan.value:
        # already subscribed to the same plan
        return RedirectResponse("/", status_code=303)

    metadata = {
        settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD: lookup_key,
    }

    checkout_session = stripe.checkout.Session.create(
        line_items=[line_item],
        mode="subscription",
        success_url=payment_processing_url,
        cancel_url=account_url,
        customer=request.user.get_or_create_stripe_customer(),
        metadata=metadata,
        subscription_data={"metadata": metadata},
        allow_promotion_codes=True,
        saved_payment_method_options={
            "payment_method_save": "enabled",
        },
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

    user.subscription.plan = plan.value
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
