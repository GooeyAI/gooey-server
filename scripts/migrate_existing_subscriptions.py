import stripe
from django.db import transaction
from loguru import logger

from app_users.models import AppUser, PaymentProvider
from payments.models import Subscription
from payments.plans import PricingPlan


USER_SUBSCRIPTION_METADATA_FIELD = "subscription_key"
ADDON_CREDITS_PER_DOLLAR = 100

# legacy data ...
available_subscriptions = {
    "addon": {
        "display": {
            "name": "Add-on",
            "title": "Top up Credits",
            "description": f"Buy a one-time top up @ {ADDON_CREDITS_PER_DOLLAR} Credits per dollar.",
        },
        "stripe": {
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Gooey.AI Add-on Credits",
                },
                "unit_amount_decimal": (ADDON_CREDITS_PER_DOLLAR / 100),  # in cents
            },
            # "quantity": 1000,  # number of credits (set by html)
            "adjustable_quantity": {
                "enabled": True,
                "maximum": 100_000,
                "minimum": 1_000,
            },
        },
    },
    "basic": {
        "display": {
            "name": "Basic Plan",
            "title": "$10/Month",
            "description": "Buy a monthly plan for $10 and get new 1500 credits (~300 runs) every month.",
        },
        "stripe": {
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Gooey.AI Basic Plan",
                },
                "unit_amount_decimal": 0.6666,  # in cents
                "recurring": {
                    "interval": "month",
                },
            },
            "quantity": 1500,  # number of credits
        },
    },
    "premium": {
        "display": {
            "name": "Premium Plan",
            "title": "$50/month + Bots",
            "description": '10000 Credits (~2000 runs) for $50/month. Includes special access to build bespoke, embeddable <a href="/video-bots/">videobots</a>.',
        },
        "stripe": {
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Gooey.AI Premium Plan",
                },
                "unit_amount_decimal": 0.5,  # in cents
                "recurring": {
                    "interval": "month",
                },
            },
            "quantity": 10000,  # number of credits
        },
    },
}


def run():
    # list active stripe subscriptions
    for sub in stripe.Subscription.list(
        limit=100,
        expand=["data.customer"],
    ).data:
        if (
            sub.metadata.get(USER_SUBSCRIPTION_METADATA_FIELD)
            in available_subscriptions
        ):
            try:
                uid = sub.customer.metadata.uid
            except AttributeError:
                uid = None
            if not uid:
                logger.error(
                    f"User not found for subscription={sub.id} customer={sub.customer.id}"
                )
                continue

            user = AppUser.objects.get_or_create_from_uid(uid)[0]
            if user.subscription:
                if (
                    user.subscription.payment_provider == PaymentProvider.STRIPE
                    and user.subscription.external_id == sub.id
                ):
                    logger.info(f"Same subscription already exists for {user.uid}")
                else:
                    logger.critical(
                        f"[Manual Action Required] User {user.uid} has two active subscriptions:"
                        f"(Stripe, {sub.id}) and ({PaymentProvider(user.subscription.payment_provider).label}, {user.subscription.external_id})"
                    )
                continue

            prod = stripe.Product.retrieve(sub.plan.product)
            plan = PricingPlan.get_by_stripe_product(prod)
            if not plan:
                logger.critical(f"Plan not found for product {prod.id}")
                continue

            with transaction.atomic():
                user.subscription = Subscription(
                    plan=plan.db_value,
                    payment_provider=PaymentProvider.STRIPE,
                    external_id=sub.id,
                    auto_recharge_enabled=False,
                )
                user.subscription.full_clean()
                user.subscription.save()
                user.save(update_fields=["subscription"])

            logger.info(f"Updated subscription for {user.uid}")
