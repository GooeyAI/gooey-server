import base64
import typing
from time import time

from furl import furl
import requests
import stripe

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.redis_cache import get_redis_cache


def make_stripe_recurring_plan(
    product_name: str,
    credits: int,
    amount: int | float,
) -> dict[str, typing.Any]:
    """
    amount is in USD
    """
    cents_per_month = amount * 100
    return {
        "currency": "usd",
        "product_data": {
            "name": product_name,
        },
        "unit_amount_decimal": round(cents_per_month / credits, 4),
        "recurring": {
            "interval": "month",
        },
    }


def make_paypal_recurring_plan(
    plan_id: str, credits: int, amount: int | float
) -> dict[str, typing.Any]:
    """
    Amount can have only 2 decimal places at most.
    """
    return {
        "plan_id": plan_id,
        "plan": {
            "billing_cycles": [
                {
                    "pricing_scheme": {
                        "fixed_price": {
                            "value": str(amount),  # in dollars
                            "currency_code": "USD",
                        },
                    },
                    "sequence": 1,
                    "total_cycles": 0,
                }
            ],
        },
        "quantity": credits,  # number of credits
    }


def cancel_stripe_subscription(subscription_id: str) -> None:
    stripe.Subscription.delete(subscription_id)


def cancel_paypal_subscription(
    subscription_id: str, reason: str = "Cancellation Requested"
) -> None:
    r = requests.post(
        str(
            furl(settings.PAYPAL_BASE)
            / "v1/billing/subscriptions"
            / subscription_id
            / "cancel"
        ),
        headers={"Authorization": generate_paypal_auth_header()},
        json={"reason": reason},
    )
    raise_for_status(r)


def generate_paypal_auth_header() -> str:
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
