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
                "maximum": 50_000,
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


def get_user_subscription(user: AppUser):
    customer = user.search_stripe_customer()
    if not customer:
        return
    subscriptions = stripe.Subscription.list(customer=customer).data
    for sub in subscriptions:
        try:
            lookup_key = sub.metadata[USER_SUBSCRIPTION_METADATA_FIELD]
            return available_subscriptions[lookup_key]
        except KeyError:
            pass


def run():
    # list active stripe subscriptions
    for sub in stripe.Subscription.list().data:
        if (
            sub.metadata.get(USER_SUBSCRIPTION_METADATA_FIELD)
            in available_subscriptions
        ):
            sub = stripe.Subscription.retrieve(sub.id)
            try:
                user = AppUser.objects.get(stripe_customer_id=sub.customer)
            except AppUser.DoesNotExist:
                logger.warning(f"User not found for subscription {sub.id}")
                continue

            prod = stripe.Product.retrieve(sub.plan.product)
            plan = PricingPlan.get_by_stripe_product(prod)
            if not plan:
                logger.warning(f"Plan not found for product {prod.id}")
                continue

            with transaction.atomic():
                user.subscription = Subscription(
                    plan=plan.value,
                    payment_provider=PaymentProvider.STRIPE,
                    external_id=sub.id,
                )
                user.subscription.full_clean()
                user.subscription.save()

                user.save(update_fields=["subscription"])

            logger.info(f"Updated subscription for {user.uid}")
