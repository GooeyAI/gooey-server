from __future__ import annotations

import base64
from datetime import datetime
from time import time
from typing import Any, Literal, Mapping, Type, TypeVar

import requests
from furl import furl
from loguru import logger
from pydantic import BaseModel, Field, ValidationError

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.redis_cache import get_redis_cache


T = TypeVar("T", bound="PaypalResource")


class PaypalResource(BaseModel):
    _api_endpoint: str | None = None
    _api_list_items_key: str | None = None

    id: str
    create_time: datetime
    update_time: datetime | None
    links: list

    @classmethod
    def list(cls: Type[T], list_all: bool = False, **params) -> list[T]:
        if not list_all:
            return cls._list(**params)

        page_size = 20
        result = []
        params.update(page_size=page_size, total_required=True)
        items_key = cls._get_api_list_items_key()
        for page in range(1, 6):
            # return maximum of 20 x 5 = 100 items
            r = requests.get(
                str(furl(settings.PAYPAL_BASE) / cls._api_endpoint),
                headers=get_default_headers(),
                params=params | {"page": page},
            )
            raise_for_status(r)
            body = r.json()
            result += [cls.parse_obj(item) for item in body[items_key]]
            if page * page_size >= body["total_items"]:
                break

        return result

    @classmethod
    def _list(cls: Type[T], **params) -> list[T]:
        if not cls._api_endpoint:
            raise NotImplementedError(f"API endpoint not defined for {cls.__name__}")

        r = requests.get(
            str(furl(settings.PAYPAL_BASE) / cls._api_endpoint),
            headers=get_default_headers(),
            params=params,
        )
        raise_for_status(r)
        return [
            cls.parse_obj(item)
            for item in r.json().get(cls._get_api_list_items_key(), [])
        ]

    @classmethod
    def retrieve(cls: Type[T], resource_id: str) -> T:
        if not cls._api_endpoint:
            raise NotImplementedError(f"API endpoint not defined for {cls.__name__}")

        r = requests.get(
            str(furl(settings.PAYPAL_BASE) / cls._api_endpoint / resource_id),
            headers=get_default_headers(),
        )
        raise_for_status(r)
        return cls.parse_obj(r.json())

    @classmethod
    def create(cls: Type[T], **data) -> T:
        if not cls._api_endpoint:
            raise NotImplementedError(f"API endpoint not defined for {cls.__name__}")

        r = requests.post(
            str(furl(settings.PAYPAL_BASE) / cls._api_endpoint),
            headers=get_default_headers(),
            json=data,
        )
        raise_for_status(r)
        return cls.parse_obj(r.json())

    @classmethod
    def _get_api_list_items_key(cls) -> str:
        return cls._api_list_items_key or cls.__name__.lower() + "s"

    def get_resource_url(self) -> furl:
        if not self._api_endpoint:
            raise NotImplementedError(
                f"API endpoint not defined for {self.__class__.__name__}"
            )

        return furl(settings.PAYPAL_BASE) / self._api_endpoint / self.id


class AmountV1(BaseModel):
    total: float
    currency: str


class Amount(BaseModel):
    value: str
    currency_code: str

    @classmethod
    def USD(cls, amount: int | float) -> Amount:
        return cls(value=str(amount), currency_code="USD")


class Subscriber(BaseModel):
    email_address: str | None
    payment_source: dict | None


class InlinePaymentInfo(BaseModel):
    status: (
        Literal["COMPLETED", "DECLINED", "PARTIALLY_REFUNDED", "PENDING", "REFUNDED"]
        | None
    )
    amount: Amount
    time: datetime


class BillingInfo(BaseModel):
    outstanding_balance: Amount
    failed_payments_count: int
    next_billing_time: datetime | None
    last_payment: InlinePaymentInfo | None


class Subscription(PaypalResource):
    _api_endpoint = "v1/billing/subscriptions"

    plan_id: str | None
    status: Literal[
        "APPROVAL_PENDING", "APPROVED", "ACTIVE", "SUSPENDED", "CANCELLED", "EXPIRED"
    ]
    custom_id: str | None
    start_date: str | None
    quantity: str | None
    plan_overridden: bool = False
    subscriber: Subscriber | None
    billing_info: BillingInfo | None

    def cancel(self, *, reason: str = "cancellation_requested") -> None:
        r = requests.post(
            str(self.get_resource_url() / "cancel"),
            headers=get_default_headers(),
            json={"reason": reason},
        )
        raise_for_status(r)

    def set_outstanding_balance(self, *, amount: Amount) -> None:
        """
        Set the outstanding balance on a subscription. This can then be charged for with /capture.
        """
        r = requests.patch(
            str(self.get_resource_url()),
            headers=get_default_headers(),
            json=[
                {
                    "op": "replace",
                    "path": "/billing_info/outstanding_balance",
                    "value": amount.dict(),
                }
            ],
        )
        raise_for_status(r)

    def update_plan(
        self,
        *,
        plan_id: str,
        plan: dict[str, Any] | None = None,
        application_context: dict[str, Any] | None = None,
    ) -> str:
        """
        Revise the plan on a subscription. Returns approval link.
        """
        r = requests.post(
            str(self.get_resource_url() / "revise"),
            headers=get_default_headers(),
            json={
                "plan_id": plan_id,
                "plan": plan or {},
                "application_context": application_context or {},
            },
        )
        raise_for_status(r)
        links = r.json().get("links", [])
        for link in links:
            if link["rel"] == "approve":
                return link["href"]

        raise ValueError("Approval link not found")

    def capture(
        self, *, note: str, amount: Amount, capture_type: str = "OUTSTANDING_BALANCE"
    ) -> None:
        """
        Fully/partially capture outstanding payment on subscription.
        """
        r = requests.post(
            str(self.get_resource_url() / "capture"),
            headers=get_default_headers(),
            json={
                "note": note,
                "amount": amount.dict(),
                "capture_type": capture_type,
            },
        )
        raise_for_status(r)


class Plan(PaypalResource):
    _api_endpoint = "v1/billing/plans"

    name: str
    status: Literal["CREATED", "ACTIVE", "INACTIVE"]
    product_id: str | None
    billing_cycles: list[dict[str, Any]] | None


class Product(PaypalResource):
    _api_endpoint = "v1/catalogs/products"

    name: str
    type: Literal["PHYSICAL", "DIGITAL", "SERVICE"] | None
    description: str | None


class Sale(PaypalResource):
    _api_endpoint = "v1/payments/sale"

    amount: AmountV1
    state: str | None
    payment_mode: str | None
    parent_payment: str | None
    custom: str | None
    billing_agreement_id: str | None


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
        headers=get_default_headers(),
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


def get_default_headers() -> dict[str, str]:
    return {
        "Authorization": generate_auth_header(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
