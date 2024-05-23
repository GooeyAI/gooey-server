import typing


def make_stripe_recurring_plan(
    credits: int,
    amount: int | float,
    *,
    product_name: str | None = None,
    product_id: str | None = None,
) -> dict[str, typing.Any]:
    """
    amount is in USD
    """
    if not product_id and not product_name:
        raise ValueError("Either product_id or product_name is required")

    cents_per_month = amount * 100
    price_data = {
        "currency": "usd",
        "unit_amount_decimal": round(cents_per_month / credits, 4),
        "recurring": {"interval": "month"},
    }
    if product_id:
        price_data["product"] = product_id
    elif product_name:
        price_data["product_data"] = {"name": product_name}

    return {
        "price_data": price_data,
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
