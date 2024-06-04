import json
from datetime import datetime
from typing import Literal

import pydantic
import requests
from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from furl import furl
from loguru import logger
from pydantic import BaseModel

from app_users.models import AppUser, PaymentProvider
from daras_ai_v2 import paypal, settings
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.fastapi_tricks import fastapi_request_json, get_route_url
from payments.models import PricingPlan
from routers.billing import (
    paypal_handle_subscription_updated,
    send_monthly_spending_notification_email,
    payment_processing_route,
    account_route,
)

router = APIRouter()


class SubscriptionPayload(BaseModel):
    lookup_key: str


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
    resource: paypal.Sale


class SubscriptionEvent(BaseWebhookEvent):
    resource_type: Literal["subscription"]
    event_type: Literal[
        "BILLING.SUBSCRIPTION.ACTIVATED",
        "BILLING.SUBSCRIPTION.CANCELLED",
        "BILLING.SUBSCRIPTION.EXPIRED",
        "BILLING.SUBSCRIPTION.UPDATED",
    ]
    resource: paypal.Subscription


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
            "Authorization": paypal.generate_auth_header(),
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

    lookup_key = SubscriptionPayload.parse_obj(payload).lookup_key
    plan = PricingPlan.get_by_key(lookup_key)
    if plan is None or not plan.monthly_charge:
        return JSONResponse(
            {"error": "Invalid plan key or not supported by PayPal"}, status_code=400
        )

    if plan.deprecated:
        return JSONResponse({"error": "Deprecated plan"}, status_code=400)

    if request.user.subscription:
        return JSONResponse(
            {"error": "User already has an active subscription"}, status_code=400
        )

    paypal_plan_info = plan.get_paypal_plan()
    pp_subscription = paypal.Subscription.create(
        plan_id=paypal_plan_info["plan_id"],
        custom_id=request.user.uid,
        plan=paypal_plan_info.get("plan", {}),
        application_context={
            "brand_name": "Gooey.AI",
            "shipping_preference": "NO_SHIPPING",
            "return_url": get_route_url(payment_processing_route),
            "cancel_url": get_route_url(account_route),
        },
    )
    return JSONResponse(content=jsonable_encoder(pp_subscription), status_code=200)


@router.post("/__/paypal/webhook/")
def webhook(request: Request, payload: dict = fastapi_request_json):
    if not paypal.verify_webhook_event(payload, headers=request.headers):
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
        case "BILLING.SUBSCRIPTION.ACTIVATED" | "BILLING.SUBSCRIPTION.UPDATED":
            event = SubscriptionEvent.parse_obj(event)
            paypal_handle_subscription_updated(event.resource)
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
            "Authorization": paypal.generate_auth_header(),
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
        headers={"Authorization": paypal.generate_auth_header()},
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
    if not sale.billing_agreement_id:
        logger.warning(f"Sale {sale.id} is missing subscription ID")
        return

    pp_subscription = paypal.Subscription.retrieve(sale.billing_agreement_id)
    if not pp_subscription.custom_id:
        logger.error(f"Subscription {pp_subscription.id} is missing custom ID")
        return

    assert pp_subscription.plan_id, "Subscription is missing plan ID"
    plan = PricingPlan.get_by_paypal_plan_id(pp_subscription.plan_id)
    if not plan:
        logger.error(f"Invalid plan ID: {pp_subscription.plan_id}")
        return

    if float(sale.amount.total) == float(plan.monthly_charge):
        new_credits = plan.credits
    else:
        new_credits = int(float(sale.amount.total) * settings.ADDON_CREDITS_PER_DOLLAR)

    user = AppUser.objects.get(uid=pp_subscription.custom_id)
    user.add_balance(
        payment_provider=PaymentProvider.PAYPAL,
        invoice_id=sale.id,
        amount=new_credits,
        charged_amount=int(float(sale.amount.total) * 100),
    )
    if not user.is_paying:
        user.is_paying = True
        user.save(update_fields=["is_paying"])
    if (
        user.subscription
        and user.subscription.should_send_monthly_spending_notification()
    ):
        send_monthly_spending_notification_email(user)


def _handle_subscription_cancelled(subscription: paypal.Subscription):
    user = AppUser.objects.get(uid=subscription.custom_id)
    if (
        user.subscription
        and user.subscription.payment_provider == PaymentProvider.PAYPAL
        and user.subscription.external_id == subscription.id
    ):
        user.subscription = None
        user.save()
