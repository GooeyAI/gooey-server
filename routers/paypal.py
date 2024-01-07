from urllib.parse import quote_plus

import base64
import requests
import requests
from fastapi import APIRouter, Depends
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from furl import furl
from daras_ai_v2.bots import request_json

from app_users.models import AppUser, PaymentProvider
from daras_ai_v2 import settings
from daras_ai_v2.settings import templates
from routers.billing import available_subscriptions

USER_SUBSCRIPTION_METADATA_FIELD = "subscription_key"

router = APIRouter()


def generate_access_token():
    """
    Generate an OAuth 2.0 access token for authenticating with PayPal REST APIs.
    @see https://developer.paypal.com/api/rest/authentication/
    """
    if not settings.PAYPAL_CLIENT_ID or not settings.PAYPAL_SECRET:
        raise Exception("MISSING_API_CREDENTIALS")
    auth = base64.b64encode(
        (settings.PAYPAL_CLIENT_ID + ":" + settings.PAYPAL_SECRET).encode("utf-8")
    ).decode("utf-8")
    response = requests.post(
        str(furl(settings.PAYPAL_BASE) / "v1/oauth2/token"),
        data="grant_type=client_credentials",
        headers={"Authorization": f"Basic {auth}"},
    )
    response.raise_for_status()
    data = response.json()
    return data.get("access_token")


# Create an order to start the transaction.
# @see https://developer.paypal.com/docs/api/orders/v2/#orders_create
@router.post("/__/paypal/orders/create/")
def create_order(request: Request, payload=Depends(request_json)):
    if not request.user or request.user.is_anonymous:
        return JSONResponse({}, status_code=401)

    lookup_key = "addon"
    quantity = payload["quantity"]
    unit_amount = (
        available_subscriptions[lookup_key]["stripe"]["price_data"]["unit_amount"] / 100
    )
    value = int(quantity * unit_amount)

    response = requests.post(
        str(furl(settings.PAYPAL_BASE) / "v2/checkout/orders"),
        headers={
            "Content-Type": "application/json",
            "Authorization": generate_auth_header(),
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
    response.raise_for_status()
    return JSONResponse(response.json(), response.status_code)


# Capture payment for the created order to complete the transaction.
# @see https://developer.paypal.com/docs/api/orders/v2/#orders_capture
@router.post("/__/paypal/orders/{order_id}/capture/")
def capture_order(order_id: str):
    response = requests.post(
        str(furl(settings.PAYPAL_BASE) / f"v2/checkout/orders/{order_id}/capture"),
        headers={
            "Content-Type": "application/json",
            "Authorization": generate_auth_header(),
            # Uncomment one of these to force an error for negative testing (in sandbox mode only). Documentation:
            # https://developer.paypal.com/tools/sandbox/negative-testing/request-headers/
            # "PayPal-Mock-Response": '{"mock_application_codes": "INSTRUMENT_DECLINED"}'
            # "PayPal-Mock-Response": '{"mock_application_codes": "TRANSACTION_REFUSED"}'
            # "PayPal-Mock-Response": '{"mock_application_codes": "INTERNAL_SERVER_ERROR"}'
        },
    )
    _handle_invoice_paid(order_id)
    return JSONResponse(response.json(), response.status_code)


async def request_body(request: Request):
    return await request.body()


def generate_auth_header() -> str:
    """
    Generate an OAuth 2.0 access token for authenticating with PayPal REST APIs.
    @see https://developer.paypal.com/api/rest/authentication/
    """
    assert (
        settings.PAYPAL_CLIENT_ID and settings.PAYPAL_SECRET
    ), "Missing API Credentials"
    auth = base64.b64encode(
        (settings.PAYPAL_CLIENT_ID + ":" + settings.PAYPAL_SECRET).encode()
    ).decode()
    response = requests.post(
        str(furl(settings.PAYPAL_BASE) / "v1/oauth2/token"),
        data="grant_type=client_credentials",
        headers={"Authorization": f"Basic {auth}"},
    )
    response.raise_for_status()
    data = response.json()
    access_token = data.get("access_token")
    assert access_token, "Missing access token in response"
    return f"Bearer " + access_token


def _handle_invoice_paid(order_id: str):
    response = requests.get(
        str(furl(settings.PAYPAL_BASE) / f"v2/checkout/orders/{order_id}"),
        headers={"Authorization": generate_auth_header()},
    )
    response.raise_for_status()
    order = response.json()
    purchase_unit = order["purchase_units"][0]
    uid = purchase_unit["payments"]["captures"][0]["custom_id"]
    user = AppUser.objects.get_or_create_from_uid(uid)[0]
    print("purchaseeee", purchase_unit)
    user.add_balance(
        payment_provider=PaymentProvider.PAYPAL,
        invoice_id=order_id,
        amount=int(purchase_unit["items"][0]["quantity"]),
        charged_amount=int(float(purchase_unit["amount"]["value"]) * 100),
    )
    if not user.is_paying:
        user.is_paying = True
        user.save(update_fields=["is_paying"])
