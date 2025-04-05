from __future__ import annotations

import typing
from enum import Enum
from textwrap import dedent
from typing import Any

import stripe
from furl import furl

from daras_ai_v2 import paypal, settings
from .utils import make_stripe_recurring_plan, make_paypal_recurring_plan

STRIPE_PRODUCT_NAMES = {
    "basic": "Gooey.AI Basic Plan",
    "premium": "Gooey.AI Premium Plan",
}
REVERSE_STRIPE_PRODUCT_NAMES = {v: k for k, v in STRIPE_PRODUCT_NAMES.items()}

if typing.TYPE_CHECKING:
    from payments.models import Subscription


class PricingPlanData(typing.NamedTuple):
    db_value: int
    key: str
    title: str
    description: str
    monthly_charge: int
    credits: int
    long_description: str = ""
    footer: str = ""
    deprecated: bool = False
    contact_us_link: str | None = None  # For Special/Enterprise plans

    pricing_title: str | None = None
    pricing_caption: str | None = None

    def get_pricing_title(self) -> str:
        if self.pricing_title is not None:
            return self.pricing_title
        else:
            return f"${self.monthly_charge} / month"

    def get_pricing_caption(self) -> str:
        if self.pricing_caption is not None:
            return self.pricing_caption
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
        pricing_caption="10,000 Credits / month + Bots",
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
        deprecated=True,
    )

    BUSINESS_2024 = PricingPlanData(
        db_value=5,
        key="business",
        title="Business (2024)",
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
        deprecated=True,
    )

    # -- active
    STARTER = PricingPlanData(
        db_value=3,
        key="starter",
        title="Pay as you go",
        description="Everyone at first, cash-strapped startups, open source developers.",
        credits=settings.VERIFIED_EMAIL_USER_FREE_CREDITS,
        monthly_charge=0,
        long_description=dedent(
            f"""
            #### Features
            <ul class="text-muted">
              <li>Public Workflows</li>
              <li>One public workspace (up to 5 members)</li>
              <li>Run all frontier models</li>
              <li><a href="/explore">Explore, fork & run</a> any public workflow</li>
              <li>Best in class RAG & agentic flows</li>
              <li>Run any code via <a href="/functions/" target="_blank">functions</a></li>
              <li>Test and deploy via <a href="/copilot/" target="_blank">Copilot</a> Web Widget</li>
              <li><a href="/speech/" target="_blank">Speech Recognition</a> and translation for 1000+ languages</li>
              <li>API access</li>
              <li>Use-case specific, golden QnA based <a href="/bulk/">bulk evaluation</a></li>
              <li>Basic usage and interaction history export and dashboards</li>
              <li>
                Broad selection of <a href="/tts/">Text to Speech voices</a> and custom 11Labs voices for
                <a href="/Lipsync/">Lipsync</a> and <a href="/copilot/">Copilot</a>
              </li>
            </ul>
            """
        ),
        footer=dedent(
            """
            <ul class="text-muted">
              <li>Non-commercial license</li>
              <li>Community Support in Discord</li>
              <li>Up to 5,000 runs of any Workflow</li>
              <br/>
            </ul>
            """
        ),
        pricing_caption=f"{settings.VERIFIED_EMAIL_USER_FREE_CREDITS:,} free credits. 1000 for $10 thereafter.",
    )

    BUSINESS = PricingPlanData(
        db_value=7,
        key="business_2025",
        title="Business",
        description="Small to mid-sized organizations, DIY teams with awesome AI ambition.",
        pricing_caption="One Private Workspace + 10,000 credits/month",
        monthly_charge=399,
        credits=10_000,
        long_description=dedent(
            """
            #### Everything in Free +
            <ul class="text-muted">
              <li>Private Workflows</li>
              <li>1 Private Workspace (up to 5 members)</li>
              <li>Collaborate on Workflows with version history</li>
              <li>SOC2, GDPR compliance, Level 5 API support from OpenAI and others</li>
              <li>API secrets for secure connections to external services</li>
              <li>Higher submission rate and concurrency limits</li>
              <li>Bring your own WhatsApp number</li>
            </ul>
            """
        ),
        footer=dedent(
            """
            <ul class="text-muted">
              <li>Commercial license</li>
              <li>Premium support via dedicated Discord Channel</li>
              <li>Up to 20,000 runs of any Workflow</li>
            </ul>
            """
        ),
    )

    ENTERPRISE = PricingPlanData(
        db_value=6,
        key="enterprise",
        title="Enterprise",
        description="For organizations ready for transformation with Gooey.AI as the foundation of their AI strategy.",
        monthly_charge=0,
        credits=999_999,
        pricing_title="Custom",
        pricing_caption="Typically $25,000 - $500,000 annually",
        long_description=dedent(
            """
            #### Everything in Business +
            <ul class="text-muted">
              <li>Unlimited Workspaces for private collaboration among teams and clients</li>
              <li>Custom inference queues and rate limits</li>
              <li>Strategic AI consulting</li>
              <li>Accelerator and GoTo Market partnerships</li>
              <li>Organizational onboarding with founders</li>
              <li>White label Workspaces for client engagement</li>
              <li>Custom Workflow evaluation and optimization</li>
              <li>Custom model training, tuning, and hosting</li>
              <li>Tailored usage and interaction analytics</li>
              <li>SMS and TTS Telephony for Copilots</li>
              <li>Use your own keys for OpenAI, Azure, and others</li>
              <li>On-prem deployment</li>
              <li>Custom workflows & feature development</li>
            </ul>
            """
        ),
        footer=dedent(
            """
            <ul class="text-muted">
              <li>Commercial & reseller license</li>
              <li>Support via Zoom, dedicated support channels, and SLA</li>
              <li>Unlimited API calls</li>
            </ul>
            """
        ),
        contact_us_link=str(furl("mailto:") / settings.SALES_EMAIL),
    )

    def __ge__(self, other: PricingPlan) -> bool:
        return self == other or self > other

    def __gt__(self, other: PricingPlan) -> bool:
        return not self == other and (
            self == PricingPlan.ENTERPRISE or self.monthly_charge > other.monthly_charge
        )

    def __le__(self, other: PricingPlan) -> bool:
        return not self > other

    def __lt__(self, other: PricingPlan) -> bool:
        return not self >= other

    @classmethod
    def db_choices(cls):
        return [(plan.db_value, plan.title) for plan in cls]

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
    def get_by_key(cls, key: str) -> PricingPlan | None:
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
