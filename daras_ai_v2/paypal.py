from __future__ import annotations

import base64
from datetime import datetime
from time import time
from typing import Any, Literal, Mapping

import requests
from furl import furl
from loguru import logger
from pydantic import BaseModel, Field, ValidationError

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.redis_cache import get_redis_cache


class PaypalResource(BaseModel):
    _api_endpoint: str | None = None

    id: str
    create_time: datetime
    update_time: datetime | None
    links: list

    @classmethod
    def retrieve(cls, resource_id: str):
        if not cls._api_endpoint:
            raise NotImplementedError(f"API endpoint not defined for {cls.__name__}")

        r = requests.get(
            str(furl(settings.PAYPAL_BASE) / cls._api_endpoint / resource_id),
            headers={"Authorization": generate_auth_header()},
        )
        raise_for_status(r)
        return cls.parse_obj(r.json())


class Amount(BaseModel):
    total: str
    currency: str


class Subscriber(PaypalResource):
    email_address: str | None
    payment_source: dict | None


class Subscription(PaypalResource):
    _api_endpoint = "v1/billing/subscriptions"

    plan_id: str
    status: Literal[
        "APPROVAL_PENDING", "APPROVED", "ACTIVE", "SUSPENDED", "CANCELLED", "EXPIRED"
    ]
    custom_id: str | None
    start_date: str | None
    quantity: str
    plan_overridden: bool = False
    subscriber: Subscriber | None

    def cancel(self, *, reason: str) -> None:
        r = requests.post(
            str(furl(settings.PAYPAL_BASE) / self._api_endpoint / self.id),
            headers={"Authorization": generate_auth_header()},
            json={"reason": reason},
        )
        raise_for_status(r)


class Sale(PaypalResource):
    _api_endpoint = "v1/payments/sale"

    amount: Amount
    state: str | None
    payment_mode: str | None
    parent_payment: str | None
    custom: str | None
    billing_agreement_id: str | None = Field(alias="subscription_id")


class PaypalWebhookHeaders(BaseModel):
    PAYPAL_AUTH_ALGO: str = Field(alias="paypal-auth-algo")
    PAYPAL_CERT_URL: str = Field(alias="paypal-cert-url")
    PAYPAL_TRANSMISSION_ID: str = Field(alias="paypal-transmission-id")
    PAYPAL_TRANSMISSION_SIG: str = Field(alias="paypal-transmission-sig")
    PAYPAL_TRANSMISSION_TIME: str = Field(alias="paypal-transmission-time")


def verify_webhook_event(event: dict, *, headers: Mapping) -> bool:
    """
    Verify the webhook event signature.
    @see https://developer.paypal.com/docs/api-basics/notifications/webhooks/rest/#verify-webhook-signature
    """
    try:
        validated_headers = PaypalWebhookHeaders.parse_obj(headers)
    except ValidationError as e:
        logger.error(f"Invalid PayPal webhook headers: {e}")
        return False

    response = requests.post(
        str(furl(settings.PAYPAL_BASE) / "v1/notifications/verify-webhook-signature"),
        headers={
            "Authorization": generate_auth_header(),
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


def generate_auth_header() -> str:
    """
    Generate an OAuth 2.0 access token for authenticating with PayPal REST APIs.
    @see https://developer.paypal.com/api/rest/authentication/
    """
    assert (
        settings.PAYPAL_CLIENT_ID and settings.PAYPAL_SECRET
    ), "Missing API Credentials"
    auth = base64.b64encode(
        f"{settings.PAYPAL_CLIENT_ID}:{settings.PAYPAL_SECRET}".encode()
    ).decode()
    redis_cache = get_redis_cache()

    # to reset token: $ redis-cli --scan --pattern 'gooey/paypal-access-token/*' | xargs redis-cli unlink
    cache_key = f"gooey/paypal-access-token/v1/{auth}"
    cache_val = redis_cache.get(cache_key)
    if cache_val:
        access_token = cache_val.decode()
    else:
        s = time()
        response = requests.post(
            str(furl(settings.PAYPAL_BASE) / "v1/oauth2/token"),
            data="grant_type=client_credentials",
            headers={"Authorization": f"Basic {auth}"},
        )
        raise_for_status(response)
        data = response.json()
        access_token = data.get("access_token")
        assert access_token, "Missing access token in response"
        # expiry with a buffer of the time taken to fetch the token + 5 minutes
        expiry = int((data.get("expires_in") or 600) - (time() - s + 300))
        redis_cache.set(cache_key, access_token.encode(), ex=expiry)

    return f"Bearer {access_token}"


def get_nested(d: dict, *keys: str, default: Any = None):
    match keys:
        case [key]:
            return d.get(key, default)
        case [key, *rest]:
            if key not in d:
                return default
            return get_nested(d[key], *rest, default=default)
        case _:
            raise ValueError("Invalid keys")
