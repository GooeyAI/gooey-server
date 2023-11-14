from urllib.parse import quote_plus

import base64
import requests
import requests
from fastapi import APIRouter, Depends
from fastapi.requests import Request
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from furl import furl
from starlette.datastructures import FormData
from sentry_sdk import capture_exception
import json

from app_users.models import AppUser
from daras_ai_v2 import settings
from daras_ai_v2.settings import templates

USER_SUBSCRIPTION_METADATA_FIELD = "subscription_key"

router = APIRouter()


def generateAccessToken():
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
        f"{settings.PAYPAL_BASE}/v1/oauth2/token",
        data="grant_type=client_credentials",
        headers={"Authorization": f"Basic {auth}"},
    )
    response.raise_for_status()
    data = response.json()
    return data.get("access_token")


# Create an order to start the transaction.
# @see https://developer.paypal.com/docs/api/orders/v2/#orders_create
def createOrder(cart, uid):
    # use the cart information passed from the front-end to calculate the purchase unit details
    print(
        "shopping cart information passed from the frontend createOrder() callback:",
        cart,
    )

    accessToken = generateAccessToken()
    url = f"{settings.PAYPAL_BASE}/v2/checkout/orders"
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": "USD",
                    "value": "0.01",
                },
                "custom_id": uid + "," + str(100),
            },
        ],
    }

    response = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {accessToken}",
            # Uncomment one of these to force an error for negative testing (in sandbox mode only). Documentation:
            # https://developer.paypal.com/tools/sandbox/negative-testing/request-headers/
            # "PayPal-Mock-Response": '{"mock_application_codes": "MISSING_REQUIRED_PARAMETER"}'
            # "PayPal-Mock-Response": '{"mock_application_codes": "PERMISSION_DENIED"}'
            # "PayPal-Mock-Response": '{"mock_application_codes": "INTERNAL_SERVER_ERROR"}'
        },
        json=payload,
    )
    return handleResponse(response)


# Capture payment for the created order to complete the transaction.
# @see https://developer.paypal.com/docs/api/orders/v2/#orders_capture
def captureOrder(orderID):
    accessToken = generateAccessToken()
    url = f"{settings.PAYPAL_BASE}/v2/checkout/orders/{orderID}/capture"

    response = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {accessToken}",
            # Uncomment one of these to force an error for negative testing (in sandbox mode only). Documentation:
            # https://developer.paypal.com/tools/sandbox/negative-testing/request-headers/
            # "PayPal-Mock-Response": '{"mock_application_codes": "INSTRUMENT_DECLINED"}'
            # "PayPal-Mock-Response": '{"mock_application_codes": "TRANSACTION_REFUSED"}'
            # "PayPal-Mock-Response": '{"mock_application_codes": "INTERNAL_SERVER_ERROR"}'
        },
    )
    return handleResponse(response)


def handleResponse(response):
    jsonResponse = response.json()
    return (jsonResponse, response.status_code)


@router.post("/__/paypal/orders/{uid}")
def orders(req: Request, uid: str):
    # use the cart information passed from the front-end to calculate the order amount detals
    cart = None  # req.text()
    print("shopping cart information passed from the frontend orders() callback:", cart)
    jsonResponse, httpStatusCode = createOrder(cart, uid)
    return JSONResponse(jsonResponse, httpStatusCode)


@router.post("/__/paypal/orders/{orderID}/capture")
def capture(req: Request, orderID: str):
    print("orderiddd", orderID)
    jsonResponse, httpStatusCode = captureOrder(orderID)
    return JSONResponse(jsonResponse, httpStatusCode)


@router.get("/paypal/")
def create_payment(request: Request):
    context = {"request": request, "settings": settings}
    return templates.TemplateResponse("create_payment.html", context)


async def request_body(request: Request):
    return await request.body()


@router.post("/__/paypal/webhook", status_code=200)
def create_webhook(request: Request, _payload: bytes = Depends(request_body)):
    print("initial payload", _payload)
    print("request.headers", request.headers)
    # Verify
    accessToken = generateAccessToken()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {accessToken}",
    }

    payload: dict = json.loads(_payload)
    print("payload", payload)
    data = {
        "transmission_id": request.headers["paypal-transmission-id"],
        "transmission_time": request.headers["paypal-transmission-time"],
        "cert_url": request.headers["paypal-cert-url"],
        "auth_algo": request.headers["paypal-auth-algo"],
        "transmission_sig": request.headers["paypal-transmission-sig"],
        "webhook_id": settings.PAYPAL_WEBHOOK_ID,
        "webhook_event": payload,
    }
    print("data", data)

    response = requests.post(
        f"{settings.PAYPAL_BASE}/v1/notifications/verify-webhook-signature",
        headers=headers,
        json=data,
    )
    response.raise_for_status()
    response = response.json()
    print("response", response)
    if response["verification_status"] != "SUCCESS":
        capture_exception(Exception("PayPal webhook verification failed"))
        return JSONResponse({"status": "failure"})
    try:
        uid = payload["resource"]["custom_id"].split(",")[0]
    except KeyError:
        uid = None
    if not uid:
        return JSONResponse(
            {
                "status": "failed",
                "error": "uid not found",
            },
            status_code=400,
        )

    # Get the type of webhook event sent - used to check the status of PaymentIntents.
    match payload["event_type"]:
        case "PAYMENT.CAPTURE.COMPLETED":
            _handle_invoice_paid(uid, data)

    return JSONResponse({"status": "success"})


def _handle_invoice_paid(uid: str, invoice_data):
    invoice_id = invoice_data["transmission_id"]
    amount = int(invoice_data["webhook_event"]["resource"]["custom_id"].split(",")[1])
    user = AppUser.objects.get_or_create_from_uid(uid)[0]
    user.add_balance(amount, invoice_id)
    if not user.is_paying:
        user.is_paying = True
        user.save(update_fields=["is_paying"])
