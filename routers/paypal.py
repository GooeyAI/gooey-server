import base64
import json
import typing
from datetime import datetime
from time import time
from typing import Literal

import pydantic
import requests
from django.db import transaction
from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from furl import furl
from loguru import logger
from pydantic import BaseModel

from app_users.models import AppUser, PaymentProvider
from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.fastapi_tricks import fastapi_request_json
from payments.models import PricingPlan, Subscription
from payments.utils import generate_paypal_auth_header

router = APIRouter()


class PaypalSubscriptionPayload(BaseModel):
    plan_id: str


class PaypalResource(BaseModel):
    id: str
    create_time: datetime
    update_time: datetime | None
    links: list


class Amount(BaseModel):
    total: str
    currency: str


class Sale(PaypalResource):
    amount: Amount
    state: str | None
    payment_mode: str | None
    parent_payment: str | None
    custom: str | None
    billing_agreement_id: str | None
    # ... ignore rest of the fields


class PaypalSubscription(PaypalResource):
    custom_id: str | None
    plan_id: str
    quantity: str
    start_date: str | None
    plan_overridden: bool = False
    status: Literal[
        "APPROVAL_PENDING", "APPROVED", "ACTIVE", "SUSPENDED", "CANCELLED", "EXPIRED"
    ]
    # ... ignore rest of the fields


class BaseWebhookEvent(BaseModel):
    id: str
    summary: str
    create_time: datetime


class WebhookEvent(BaseWebhookEvent):
    resource_type: str
    event_type: str
    resource: dict


class SaleCompletedEvent(BaseWebhookEvent):
    resource_type: Literal["sale"]
    event_type: Literal["PAYMENT.SALE.COMPLETED"]
    resource: Sale


class SubscriptionEvent(BaseWebhookEvent):
    resource_type: Literal["subscription"]
    event_type: Literal[
        "BILLING.SUBSCRIPTION.ACTIVATED",
        "BILLING.SUBSCRIPTION.CANCELLED",
        "BILLING.SUBSCRIPTION.EXPIRED",
    ]
    resource: PaypalSubscription


class ValidPaypalWebhookHeaders(BaseModel):
    PAYPAL_AUTH_ALGO: str = pydantic.Field(alias="paypal-auth-algo")
    PAYPAL_CERT_URL: str = pydantic.Field(alias="paypal-cert-url")
    PAYPAL_TRANSMISSION_ID: str = pydantic.Field(alias="paypal-transmission-id")
    PAYPAL_TRANSMISSION_SIG: str = pydantic.Field(alias="paypal-transmission-sig")
    PAYPAL_TRANSMISSION_TIME: str = pydantic.Field(alias="paypal-transmission-time")


# Create an order to start the transaction.
# @see https://developer.paypal.com/docs/api/orders/v2/#orders_create
@router.post("/__/paypal/orders/create/")
def create_order(request: Request, payload: dict = fastapi_request_json):
    if not request.user or request.user.is_anonymous:
        return JSONResponse({}, status_code=401)

    quantity = payload["quantity"]
    unit_amount = 1 / settings.ADDON_CREDITS_PER_DOLLAR
    value = int(quantity * unit_amount)

    response = requests.post(
        str(furl(settings.PAYPAL_BASE) / "v2/checkout/orders"),
        headers={
            "Content-Type": "application/json",
            "Authorization": generate_paypal_auth_header(),
            # Uncomment one of these to force an error for negative testing (in sandbox mode only). Documentation:
            # https://developer.paypal.com/tools/sandbox/negative-testing/request-headers/
            # "PayPal-Mock-Response": '{"mock_application_codes": "MISSING_REQUIRED_PARAMETER"}'
            # "PayPal-Mock-Response": '{"mock_application_codes": "PERMISSION_DENIED"}'
            # "PayPal-Mock-Response": '{"mock_application_codes": "INTERNAL_SERVER_ERROR"}'
        },
        json={
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "amount": {
                        "currency_code": "USD",
                        "value": str(value),
                        "breakdown": {
                            "item_total": {
                                "currency_code": "USD",
                                "value": str(value),
                            }
                        },
                    },
                    "items": [
                        {
                            "name": "Top up Credits",
                            "quantity": str(quantity),
                            "unit_amount": {
                                "currency_code": "USD",
                                "value": str(unit_amount),
                            },
                        }
                    ],
                    "custom_id": request.user.uid,
                },
            ],
        },
    )
    raise_for_status(response)
    return JSONResponse(response.json(), response.status_code)


@router.post("/__/paypal/subscriptions/create/")
def create_subscription(request: Request, payload: dict = fastapi_request_json):
    if not request.user or request.user.is_anonymous:
        return JSONResponse({}, status_code=401)

    paypal_payload = PaypalSubscriptionPayload.parse_obj(payload)
    plan = get_pricing_plan(paypal_payload.plan_id)
    if plan is None:
        return JSONResponse({"error": "Invalid plan ID"}, status_code=400)

    response = requests.post(
        str(furl(settings.PAYPAL_BASE) / "v1/billing/subscriptions"),
        headers={"Authorization": generate_paypal_auth_header()},
        json={
            "plan_id": paypal_payload.plan_id,
            "custom_id": request.user.uid,
            "application_context": {
                "brand_name": "Gooey.AI",
                "shipping_preference": "NO_SHIPPING",
                "return_url": str(
                    furl(settings.APP_BASE_URL) / "payment-success" / "/"
                ),
                "cancel_url": str(furl(settings.APP_BASE_URL) / "account" / "/"),
            },
            "plan": plan.paypal.get("plan", {}),
        },
    )

    raise_for_status(response)
    return JSONResponse(response.json(), response.status_code)


@router.post("/__/paypal/webhook/")
def webhook(request: Request, payload: dict = fastapi_request_json):
    if not verify_webhook_event(payload, headers=request.headers):
        logger.error("Invalid PayPal webhook signature")
        return JSONResponse({"error": "Invalid signature"}, status_code=400)

    try:
        event = WebhookEvent.parse_obj(payload)
    except pydantic.ValidationError as e:
        logger.error(f"Invalid PayPal webhook payload: {json.dumps(e)}")
        return JSONResponse({"error": "Invalid event type"}, status_code=400)

    logger.info(f"Received event: {event.event_type}")

    match event.event_type:
        case "PAYMENT.SALE.COMPLETED":
            event = SaleCompletedEvent.parse_obj(event)
            _handle_sale_completed(event)
        case "BILLING.SUBSCRIPTION.ACTIVATED":
            event = SubscriptionEvent.parse_obj(event)
            _handle_subscription_updated(event.resource)
        case "BILLING.SUBSCRIPTION.CANCELLED" | "BILLING.SUBSCRIPTION.EXPIRED":
            event = SubscriptionEvent.parse_obj(event)
            _handle_subscription_cancelled(event.resource)
        case _:
            logger.error(f"Unhandled PayPal webhook event: {event.event_type}")

    return JSONResponse({}, status_code=200)


# Capture payment for the created order to complete the transaction.
# @see https://developer.paypal.com/docs/api/orders/v2/#orders_capture
@router.post("/__/paypal/orders/{order_id}/capture/")
def capture_order(order_id: str):
    response = requests.post(
        str(furl(settings.PAYPAL_BASE) / f"v2/checkout/orders/{order_id}/capture"),
        headers={
            "Content-Type": "application/json",
            "Authorization": generate_paypal_auth_header(),
            # Uncomment one of these to force an error for negative testing (in sandbox mode only). Documentation:
            # https://developer.paypal.com/tools/sandbox/negative-testing/request-headers/
            # "PayPal-Mock-Response": '{"mock_application_codes": "INSTRUMENT_DECLINED"}'
            # "PayPal-Mock-Response": '{"mock_application_codes": "TRANSACTION_REFUSED"}'
            # "PayPal-Mock-Response": '{"mock_application_codes": "INTERNAL_SERVER_ERROR"}'
        },
    )
    _handle_invoice_paid(order_id)
    return JSONResponse(response.json(), response.status_code)


def _handle_invoice_paid(order_id: str):
    response = requests.get(
        str(furl(settings.PAYPAL_BASE) / f"v2/checkout/orders/{order_id}"),
        headers={"Authorization": generate_paypal_auth_header()},
    )
    raise_for_status(response)
    order = response.json()
    purchase_unit = order["purchase_units"][0]
    uid = purchase_unit["payments"]["captures"][0]["custom_id"]
    user = AppUser.objects.get_or_create_from_uid(uid)[0]
    user.add_balance(
        payment_provider=PaymentProvider.PAYPAL,
        invoice_id=order_id,
        amount=int(purchase_unit["items"][0]["quantity"]),
        charged_amount=int(float(purchase_unit["amount"]["value"]) * 100),
    )
    if not user.is_paying:
        user.is_paying = True
        user.save(update_fields=["is_paying"])


def _handle_sale_completed(event: SaleCompletedEvent):
    sale = event.resource
    if not sale.billing_agreement_id or not sale.custom:
        logger.warning(f"Sale {sale.id} is missing billing agreement or custom ID")
        return

    user = AppUser.objects.get(uid=sale.custom)
    subscription = get_subscription_from_id(sale.billing_agreement_id)
    plan = get_pricing_plan(subscription.plan_id)
    if not plan:
        logger.error(f"Invalid plan ID: {subscription.plan_id}")
        return

    user.add_balance(
        payment_provider=PaymentProvider.PAYPAL,
        invoice_id=sale.id,
        amount=int(plan.credits),
        charged_amount=int(float(sale.amount.total) * 100),  # in cents
    )

    if not user.is_paying:
        user.is_paying = True
        user.save(update_fields=["is_paying"])


@transaction.atomic
def _handle_subscription_updated(subscription: PaypalSubscription):
    plan = get_pricing_plan(subscription.plan_id)
    if not plan:
        logger.error(f"Invalid plan ID: {subscription.plan_id}")
        return

    if not subscription.status == "ACTIVE":
        logger.warning(f"Subscription {subscription.id} is not active")
        return

    user = AppUser.objects.get(uid=subscription.custom_id)
    if (
        user.subscription
        and user.subscription.payment_provider == PaymentProvider.PAYPAL
        and user.subscription.external_id == subscription.id
    ):
        logger.warning(f"Subscription {subscription.id} already exists")
        return
    elif user.subscription:
        user.subscription.cancel()
        user.subscription = None

    user.subscription = Subscription(
        plan=plan.value,
        payment_provider=PaymentProvider.PAYPAL,
        external_id=subscription.id,
    )
    user.subscription.full_clean()
    user.subscription.save()
    user.save()


def _handle_subscription_cancelled(subscription: PaypalSubscription):
    user = AppUser.objects.get(uid=subscription.custom_id)
    if (
        user.subscription
        and user.subscription.payment_provider == PaymentProvider.PAYPAL
        and user.subscription.external_id == subscription.id
    ):
        user.subscription = None
        user.save()


def get_payment_from_id(payment_id: str):
    response = requests.get(
        str(furl(settings.PAYPAL_BASE) / f"v2/payments/{payment_id}"),
        headers={
            "Authorization": generate_paypal_auth_header(),
            "Prefer": "return=representation",
        },
    )
    raise_for_status(response)
    return response.json()


def get_sale_from_id(sale_id: str):
    response = requests.get(
        str(furl(settings.PAYPAL_BASE) / f"v1/payments/sale/{sale_id}"),
        headers={
            "Authorization": generate_paypal_auth_header(),
            "Prefer": "return=representation",
        },
    )
    raise_for_status(response)
    return Sale.parse_obj(response.json())


def get_subscription_from_id(billing_agreement_id: str) -> PaypalSubscription:
    response = requests.get(
        str(
            furl(settings.PAYPAL_BASE)
            / f"v1/billing/subscriptions/{billing_agreement_id}"
        ),
        headers={"Authorization": generate_paypal_auth_header()},
    )
    raise_for_status(response)
    return PaypalSubscription.parse_obj(response.json())


def verify_webhook_event(event: dict, *, headers: typing.Mapping) -> bool:
    """
    Verify the webhook event signature.
    @see https://developer.paypal.com/docs/api-basics/notifications/webhooks/rest/#verify-webhook-signature
    """
    try:
        validated_headers = ValidPaypalWebhookHeaders.parse_obj(headers)
    except pydantic.ValidationError as e:
        logger.error(f"Invalid PayPal webhook headers: {e}")
        return False

    response = requests.post(
        str(furl(settings.PAYPAL_BASE) / "v1/notifications/verify-webhook-signature"),
        headers={
            "Authorization": generate_paypal_auth_header(),
        },
        json={
            "auth_algo": validated_headers.PAYPAL_AUTH_ALGO,
            "cert_url": validated_headers.PAYPAL_CERT_URL,
            "transmission_id": validated_headers.PAYPAL_TRANSMISSION_ID,
            "transmission_sig": validated_headers.PAYPAL_TRANSMISSION_SIG,
            "transmission_time": validated_headers.PAYPAL_TRANSMISSION_TIME,
            "webhook_id": settings.PAYPAL_WEBHOOK_ID,
            "webhook_event": event,
        },
    )

    raise_for_status(response)
    return response.json()["verification_status"] == "SUCCESS"


def get_pricing_plan(plan_id: str) -> PricingPlan | None:
    for plan in PricingPlan:
        if plan.paypal and plan.paypal.get("plan_id") == plan_id:
            return plan
    return None
