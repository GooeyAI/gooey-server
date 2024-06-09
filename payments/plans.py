from __future__ import annotations

import typing
from enum import Enum
from textwrap import dedent
from typing import Any

import stripe

from daras_ai_v2 import paypal, settings
from .utils import make_stripe_recurring_plan, make_paypal_recurring_plan

STRIPE_PRODUCT_NAMES = {
    "basic": "Gooey.AI Basic Plan",
    "premium": "Gooey.AI Premium Plan",
}
REVERSE_STRIPE_PRODUCT_NAMES = {v: k for k, v in STRIPE_PRODUCT_NAMES.items()}


class PricingPlanData(typing.NamedTuple):
    db_value: int
    key: str
    title: str
    description: str
    monthly_charge: int
    credits: int
    long_description: str = ""
    deprecated: bool = False
    contact_us_link: str | None = None  # For Special/Enterprise plans

    title_override: str | None = None
    caption_override: str | None = None

    def pricing_title(self) -> str:
        if self.title_override is not None:
            return self.title_override
        else:
            return f"${self.monthly_charge}"

    def pricing_caption(self) -> str:
        if self.caption_override is not None:
            return self.caption_override
        else:
            return f"{self.credits:,} Credits / month"


class PricingPlan(PricingPlanData, Enum):
    # OLD --- deprecated & hidden
    BASIC = PricingPlanData(
        db_value=1,
        key="basic",
        title="Basic Plan",
        description="Buy a monthly plan for $10 and get new 1500 credits (~300 runs) every month.",
        credits=1_500,
        monthly_charge=10,
        deprecated=True,
    )
    PREMIUM = PricingPlanData(
        db_value=2,
        key="premium",
        title="Premium Plan",
        description="10000 Credits (~2000 runs) for $50/month. Includes special access to build bespoke, embeddable [videobots](/video-bots/)",
        credits=10_000,
        monthly_charge=50,
        deprecated=True,
        caption_override="10,000 Credits / month + Bots",
    )

    # -- active
    STARTER = PricingPlanData(
        db_value=3,
        key="starter",
        title="Starter",
        description="The best of private & open source AI",
        credits=settings.LOGIN_USER_FREE_CREDITS,
        monthly_charge=0,
        long_description=dedent(
            """
            **Includes (est.)**
            <ul class="text-muted">
              <li>100 Copilot Conversations  </li>
              <li>10 Lipsync minutes  </li>
              <li>33 Animation seconds  </li>
              <li>15 AI QR Codes  </li>
              <li>Non-commercial terms  </li>
            </ul>

            **Features**
            <ul class="text-muted">
              <li>Access every public workflow  </li>
              <li>WhatsApp, Slack, FB or Web Copilots  </li>
              <li>Top LLMs (GPT3.5, Mistral, LLaMA3)  </li>
              <li>API access  </li>
              <li>Community Support on Discord</li>
            </ul>
            """
        ),
        title_override="Free",
        caption_override=f"{settings.LOGIN_USER_FREE_CREDITS:,} Credits to start",
    )

    CREATOR = PricingPlanData(
        db_value=4,
        key="creator",
        title="Creator",
        description="For individuals, startups & freelancers",
        monthly_charge=20,
        credits=2_000,
        long_description=dedent(
            """
            **Includes (est.)**
            <ul class="text-muted">
              <li>400 Copilot Conversations  </li>
              <li>40 Lipsync minutes  </li>
              <li>133 Animation seconds  </li>
              <li>75 AI QR Codes  </li>
              <li>Commercial rights for small companies (<$1M revenue / year)</li>
            </ul>

            **Everything in Starter, plus**
            <ul class="text-muted">
              <li>Saved Private Workflows  </li>
              <li>Auto recharge with custom budgets  </li>
              <li>Premium LLMs (GPT 4s, Gemini, Claude)  </li>
              <li>100 MB of Knowledge  </li>
              <li>Copilot Analytics  </li>
              <li>11Labs voices for Lipsync  </li>
            </ul>
            """
        ),
    )

    BUSINESS = PricingPlanData(
        db_value=5,
        key="business",
        title="Business",
        description="For teams & commercial licenses",
        monthly_charge=199,
        credits=20_000,
        long_description=dedent(
            """
            **Includes (est.)**
            <ul class="text-muted">
              <li>4,000 Copilot Conversations</li>
              <li>400 Lipsync minutes</li>
              <li>1333 Animation seconds</li>
              <li>750 AI QR Codes</li>
              <li>Commercial rights for all companies</li>
            </ul>

            **Everything in Creator, plus**
            <ul class="text-muted">
              <li>Team Collaboration</li>
              <li>1 GB of Knowledge</li>
              <li>Early access workflows</li>
              <li>Zero-data retention options</li>
              <li>Premium Support via Slack</li>
            </ul>
            """
        ),
    )

    ENTERPRISE = PricingPlanData(
        db_value=6,
        key="enterprise",
        title="Enterprise / Agency",
        description="Unlimited access, enterprise SLAs & support",
        monthly_charge=0,
        credits=999_999,
        long_description=dedent(
            """
            **Includes**
            <ul class="text-muted">
              <li>Unlimited Copilots & Conversations  </li>
              <li>Unlimited HD Lipsync  </li>
              <li>Unlimited Animations  </li>
              <li>Bespoke QR codes & unlimited scans  </li>
              <li>Reseller rights  </li>
            </ul>

            **Everything in Business, plus**
            <ul class="text-muted">
              <li>Customized workflows</li>
              <li>Knowledge with 1000s of files</li>
              <li>Managed WhatsApp Numbers</li>
              <li>AI Consulting & Training</li>
              <li>Access Gooey.AI code & submit changes</li>
              <li>Dedicated Account Manager</li>
              <li>Group level access control</li>
              <li>On-prem & VPC installs</li>
              <li>Support via Zoom</li>
            </ul>
            """
        ),
        contact_us_link=f"mailto:{settings.SALES_EMAIL}",
        title_override="Let's talk",
        caption_override="",
    )

    def __ge__(self, other: PricingPlan) -> bool:
        return self.monthly_charge >= other.monthly_charge

    def __gt__(self, other: PricingPlan) -> bool:
        return self.monthly_charge > other.monthly_charge

    def __le__(self, other: PricingPlan) -> bool:
        return self.monthly_charge <= other.monthly_charge

    def __lt__(self, other: PricingPlan) -> bool:
        return self.monthly_charge < other.monthly_charge

    @classmethod
    def db_choices(cls):
        return [(plan.db_value, plan.name) for plan in cls]

    @classmethod
    def from_sub(cls, sub: "Subscription") -> PricingPlan:
        return cls.from_db_value(sub.plan)

    @classmethod
    def from_db_value(cls, db_value: int) -> PricingPlan:
        for plan in cls:
            if plan.db_value == db_value:
                return plan
        raise ValueError(f"Invalid {cls.__name__} {db_value=}")

    @classmethod
    def get_by_stripe_product(cls, product: stripe.Product) -> PricingPlan | None:
        if product.name in REVERSE_STRIPE_PRODUCT_NAMES:
            return cls.get_by_key(REVERSE_STRIPE_PRODUCT_NAMES[product.name])

        for plan in cls:
            if plan.supports_stripe() and plan.get_stripe_product_id() == product.id:
                return plan

    @classmethod
    def get_by_paypal_plan_id(cls, plan_id: str) -> PricingPlan | None:
        for plan in cls:
            if plan.supports_paypal() and plan.get_paypal_plan_id() == plan_id:
                return plan

    @classmethod
    def get_by_key(cls, key: str):
        for plan in cls:
            if plan.key == key:
                return plan

    def supports_stripe(self) -> bool:
        return bool(self.monthly_charge)

    def supports_paypal(self) -> bool:
        return bool(self.monthly_charge)

    def get_stripe_line_item(self) -> dict[str, Any]:
        if not self.supports_stripe():
            raise ValueError(f"Can't bill {self.title} via Stripe")

        if self.key in STRIPE_PRODUCT_NAMES:
            # via product_name
            return make_stripe_recurring_plan(
                product_name=STRIPE_PRODUCT_NAMES[self.key],
                credits=self.credits,
                amount=self.monthly_charge,
            )
        else:
            # via product_id
            return make_stripe_recurring_plan(
                product_id=self.get_stripe_product_id(),
                credits=self.credits,
                amount=self.monthly_charge,
            )

    def get_paypal_plan(self) -> dict[str, Any]:
        if not self.supports_paypal():
            raise ValueError(f"Can't bill {self.title} via PayPal")

        return make_paypal_recurring_plan(
            plan_id=self.get_paypal_plan_id(),
            credits=self.credits,
            amount=self.monthly_charge,
        )

    def get_stripe_product_id(self) -> str:
        for product in stripe.Product.list(expand=["data.default_price"]).data:
            if (
                product.default_price
                and product.default_price.unit_amount == self.monthly_charge * 100
            ):  # cents
                return product.id

        product = stripe.Product.create(
            name=self.title,
            description=self.description,
            default_price_data={
                "currency": "usd",
                "unit_amount": self.monthly_charge * 100,
                "recurring": {"interval": "month"},
            },
        )
        return product.id

    def get_paypal_plan_id(self) -> str:
        product_id = paypal_get_or_create_default_product().id

        for plan in paypal.Plan.list(list_all=True):
            if plan.status != "ACTIVE":
                continue

            plan = paypal.Plan.retrieve(plan.id)
            if value := plan.billing_cycles and plan.billing_cycles[0].get(
                "pricing_scheme", {}
            ).get("fixed_price", {}).get("value", ""):
                assert isinstance(value, str)
                if float(value) == float(self.monthly_charge):
                    return plan.id

        plan = paypal.Plan.create(
            product_id=product_id,
            name=self.title,
            description=self.description,
            billing_cycles=[
                {
                    "tenure_type": "REGULAR",
                    "pricing_scheme": {
                        "fixed_price": {
                            "value": str(self.monthly_charge),
                            "currency_code": "USD",
                        },
                    },
                    "sequence": 1,
                    "total_cycles": 0,
                    "frequency": {
                        "interval_unit": "MONTH",
                        "interval_count": 1,
                    },
                }
            ],
            payment_preferences={},
        )
        return plan.id


def paypal_get_or_create_default_product() -> paypal.Product:
    for product in paypal.Product.list():
        if product.name == settings.PAYPAL_DEFAULT_PRODUCT_NAME:
            return product

    product = paypal.Product.create(
        name=settings.PAYPAL_DEFAULT_PRODUCT_NAME,
        type="DIGITAL",
        description="Credits for using Gooey.AI",
    )
    return product


def stripe_get_addon_product() -> stripe.Product:
    for product in stripe.Product.list():
        if product.name == settings.STRIPE_ADDON_PRODUCT_NAME:
            return product

    product = stripe.Product.create(
        name=settings.STRIPE_ADDON_PRODUCT_NAME,
        description="Credits for using Gooey.AI",
    )
    return product
