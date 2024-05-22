import typing

import stripe

from daras_ai_v2 import paypal


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
        "price_data": {
            "currency": "usd",
            "product_data": {
                "name": product_name,
            },
            "unit_amount_decimal": round(cents_per_month / credits, 4),
            "recurring": {
                "interval": "month",
            },
        },
        "quantity": credits,
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
    paypal.Subscription.retrieve(subscription_id).cancel(reason=reason)
