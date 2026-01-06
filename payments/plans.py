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

if typing.TYPE_CHECKING:
    from payments.models import Subscription


class PricingTier(typing.NamedTuple):
    per_seat_credits: int
    per_seat_monthly_charge: int
    seats: int = 1

    @property
    def label(self) -> str:
        return f"{self.credits:,} Credits for ${self.monthly_charge}/month"

    @property
    def credits(self) -> int:
        return self.per_seat_credits * self.seats

    @property
    def monthly_charge(self) -> int:
        return self.per_seat_monthly_charge * self.seats


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
    tiers: list[PricingTier] | None = None  # For plans with multiple pricing tiers
    full_width: bool = False

    def get_pricing_title(self, tier: PricingTier | None = None) -> str:
        if self.pricing_title is not None:
            return self.pricing_title

        monthly_charge = self.get_active_monthly_charge(tier)
        return f"${monthly_charge}/month"

    def get_pricing_caption(self, tier: PricingTier | None = None) -> str:
        if self.pricing_caption is not None:
            return self.pricing_caption

        credits = self.get_active_credits(tier)
        return f"{credits:,} credits/month"

    def get_active_credits(self, tier: PricingTier | None = None) -> int:
        """Get credits for specific tier or default"""
        return tier and tier.credits or self.credits

    def get_active_monthly_charge(self, tier: PricingTier | None = None) -> int:
        """Get monthly charge for specific tier or default"""
        return tier and tier.monthly_charge or self.monthly_charge

    def get_default_tier(self) -> PricingTier:
        if self.tiers:
            return self.tiers[0]
        raise ValueError(f"No tiers available for plan {self.key}")


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
    BUSINESS_2025 = PricingPlanData(
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

              <li>Private Team Workspace</li>
              <li>Integrate with Google, M365, Salesforce, Notion + 100s of others</li>
              <li>API Secrets to securely access any system</li>
              <li>Bring your own WhatsApp number</li>
              <li>Embed copilots in your own App</li>
              <li>Impact and usage <a
                    href="https://gooey.ai/copilot/base-copilot-w-search-rag-code-execution-v1xm6uhp/integrations/PnM/stats/?view=Daily&details=Conversations&start_date=2025-10-15&end_date=2025-10-31&sort_by=Last+Sent"
                >dashboards</a></li>
              <li>Role Based Management</li>
              <li>Centralized billing</li>
              <li>Pooled Credits, Submission Rates and Concurrency</li>
              <li>Version History on Workflows</li>
            </ul>
            """
        ),
        footer=dedent(
            """
            <ul class="text-muted">
              <li>Full Commercial license</li>
              <li>Premium team support via Email</li>
            </ul>
            """
        ),
        deprecated=True,
    )

    # -- active
    STARTER = PricingPlanData(
        db_value=3,
        key="starter",
        title="Free",
        description="Kick our tires",
        credits=0,
        monthly_charge=0,
        long_description=dedent(
            """
            #### Features
            <ul class="text-muted">
              <li>Public Workflows</li>
              <li>Run all frontier <a href="/compare-llm">LLMs</a></li>
              <li><a href="/explore">Explore</a>, fork & run any public AI Workflow</li>
              <li>Test and deploy via <a href="/copilot/">Agent Web Widget</a></li>
              <li><a href="/speech/">Speech recognition</a> and translation for 1000+ languages</li>
              <li>Broad selection of <a href="/text-to-speech/">Text to Speech voices</a> for <a href="/lipsync/">Lipsync</a> and <a href="/copilot/">Copilot</a></li>
              <li>Access top image generation models</li>
              <li>Deploy Workflows via the Web, WhatsApp, SMS/Voice, Slack or FB</li>
              <li>Use-case specific, Workflow <a href="/bulk/">Evaluation</a> to optimize model and component selection.</li>
              <li><a href="https://docs.gooey.ai/api-reference/getting-started">API access</a></li>
            </ul>
            """
        ),
        footer=dedent(
            """
            <ul class="text-muted">
              <li>Non-commercial license</li>
              <li>Community support in Discord</li>
            </ul>
            """
        ),
        pricing_title="$0",
        pricing_caption=f"{settings.VERIFIED_EMAIL_USER_FREE_CREDITS} credits to start.",
    )

    STANDARD = PricingPlanData(
        db_value=8,
        key="standard_2025",
        title="Standard",
        description="More credits for power users",
        monthly_charge=25,
        credits=2_000,
        long_description=dedent(
            """
            #### Everything in Free +
            <ul class="text-muted">
              <li>Private Workflows</li>
              <li>Access frontier video & animation models</li>
              <li>Up to 44,000 Cr / month</li>
              <li>Increased file upload limit</li>
              <li>Higher rate limits</li>
              <li>Execute any code via JS / Python <a href="/functions/">functions</a></li>
              <li>SOC2 Type II + GDPR Compliance</li>
            </ul>
            """
        ),
        footer="""
        <ul class="text-muted">
          <li>Commercial license for images & videos</li>
          <li>Premium support via Discord</li>
        </ul>
        """,
        tiers=[
            PricingTier(per_seat_credits=2_000, per_seat_monthly_charge=25),
            PricingTier(per_seat_credits=4_200, per_seat_monthly_charge=50),
            PricingTier(per_seat_credits=9_000, per_seat_monthly_charge=100),
            PricingTier(per_seat_credits=20_000, per_seat_monthly_charge=200),
            PricingTier(per_seat_credits=32_000, per_seat_monthly_charge=300),
            PricingTier(per_seat_credits=44_000, per_seat_monthly_charge=400),
        ],
    )

    TEAM = PricingPlanData(
        db_value=9,
        key="team_2025",
        title="Team",
        description="AI Teams that collaborate together can change the world.",
        pricing_caption="Monthly credits per member",
        monthly_charge=40,
        credits=2_500,
        long_description=dedent(
            """
            #### All Free Features +
            <ul class="text-muted">
              <li>Private Team Workspace</li>
              <li>Integrate with Google, M365, Salesforce, Notion + 100s of others</li>
              <li>API Secrets to securely access any system</li>
              <li>Bring your own WhatsApp number</li>
              <li>Embed copilots in your own App</li>
              <li>Impact and usage <a href="https://gooey.ai/copilot/base-copilot-w-search-rag-code-execution-v1xm6uhp/integrations/PnM/stats/?view=Daily&details=Conversations&start_date=2025-11-09&end_date=2025-11-25&sort_by=Last+Sent">dashboards</a></li>
              <li>Role Based Management</li>
              <li>Centralized billing</li>
              <li>Pooled Credits, Submission Rates and Concurrency</li>
              <li>Version History on Workflows</li>
            </ul>
            """
        ),
        footer=dedent(
            """
            <ul class="text-muted">
              <li>Commerical license</li>
              <li>Premium Support via Email</li>
            </ul>
            """
        ),
        tiers=[
            PricingTier(per_seat_credits=2_500, per_seat_monthly_charge=40),
            PricingTier(per_seat_credits=5_000, per_seat_monthly_charge=60),
            PricingTier(per_seat_credits=9_000, per_seat_monthly_charge=110),
            PricingTier(per_seat_credits=20_000, per_seat_monthly_charge=200),
            PricingTier(per_seat_credits=32_000, per_seat_monthly_charge=300),
            PricingTier(per_seat_credits=44_000, per_seat_monthly_charge=400),
        ],
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
        full_width=True,
        long_description=dedent(
            """
            <div class="row row-cols-1 row-cols-md-2">
                <div class="col">
                  <ul class="text-muted">
                    <li>Unlimited Workspaces for private collaboration among teams and clients</li>
                    <li>Strategic AI consulting including:</li>
                    <li>Rock-bottom, full-transparency, no mark-up token pricing</li>
                    <li>Ongoing cost optimization + evals across all AI model providers</li>
                    <li>Tailored onboarding and training</li>
                    <li>Workflow performance evaluation</li>
                    <li>Bespoke Workflows & features</li>
                  </ul>
                </div>
                <div class="col">
                  <ul class="text-muted">
                    <li>Dedicated numbers for WhatsApp, Voice + SMS AI Agents</li>
                    <li>Impact + ROI dashboards for your org based on industry best practices</li>
                    <li>Export usage to your own BI platforms</li>
                    <li>Integrations with your internal systems</li>
                    <li>Host & integrate your fine-tuned model on Gooey.AI infrastructure</li>
                    <li>Use your own keys for OpenAI, Azure, and others</li>
                    <li>On-prem deployments</li>
                    <li>Custom inference queues and rate limits</li>
                  </ul>
                </div>
            </div>
            """
        ),
        contact_us_link=settings.CONTACT_URL,
    )

    def __ge__(self, other: PricingPlan) -> bool:
        return self == other or self > other

    def __gt__(self, other: PricingPlan) -> bool:
        return not self == other and (
            self == PricingPlan.ENTERPRISE
            or self.get_active_monthly_charge() > other.get_active_monthly_charge()
        )

    def __le__(self, other: PricingPlan) -> bool:
        return not self > other

    def __lt__(self, other: PricingPlan) -> bool:
        return not self >= other

    @classmethod
    def db_choices(cls):
        return [(plan.db_value, plan.title) for plan in cls]

    @classmethod
    def from_sub(cls, sub: typing.Optional["Subscription"]) -> PricingPlan:
        if sub:
            return cls.from_db_value(sub.plan)
        return cls.STARTER

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

        if product.default_price:
            product_price = product.default_price.unit_amount  # in cents
        else:
            product_price = None

        # Check all plans and their tiers by matching name and price
        for plan in cls:
            if not plan.supports_stripe():
                continue

            # Check if plan has tiers
            if plan.tiers:
                # Check each tier by matching product name
                for tier in plan.tiers:
                    expected_name = f"{plan.title} - {tier.label}"
                    expected_price = tier.monthly_charge * 100  # convert to cents

                    if product.name == expected_name and (
                        product_price is None or product_price == expected_price
                    ):
                        return plan
            else:
                # No tiers, check default plan by name match
                expected_price = plan.monthly_charge * 100  # convert to cents

                if product.name == plan.title and (
                    product_price is None or product_price == expected_price
                ):
                    return plan

        return None

    @classmethod
    def get_by_paypal_plan_id(cls, plan_id: str) -> PricingPlan | None:
        for plan in cls:
            if plan.supports_paypal() and plan.get_paypal_plan_id() == plan_id:
                return plan

    @classmethod
    def get_by_key(cls, key: str) -> PricingPlan:
        for plan in cls:
            if plan.key == key:
                return plan
        raise KeyError(f"Invalid {cls.__name__} key: {key}")

    def supports_stripe(self) -> bool:
        return bool(self.monthly_charge)

    def supports_paypal(self) -> bool:
        return bool(self.monthly_charge)

    def get_stripe_line_item(self, tier: PricingTier | None = None) -> dict[str, Any]:
        if not self.supports_stripe():
            raise ValueError(f"Can't bill {self.title} via Stripe")

        # Get pricing from tier or default
        credits = self.get_active_credits(tier)
        monthly_charge = self.get_active_monthly_charge(tier)

        if self.key in STRIPE_PRODUCT_NAMES:
            # via product_name
            return make_stripe_recurring_plan(
                product_name=STRIPE_PRODUCT_NAMES[self.key],
                credits=credits,
                amount=monthly_charge,
            )
        else:
            # via product_id
            return make_stripe_recurring_plan(
                product_id=self.get_stripe_product_id(tier),
                credits=credits,
                amount=monthly_charge,
            )

    def get_paypal_plan(self) -> dict[str, Any]:
        if not self.supports_paypal():
            raise ValueError(f"Can't bill {self.title} via PayPal")

        return make_paypal_recurring_plan(
            plan_id=self.get_paypal_plan_id(),
            credits=self.credits,
            amount=self.monthly_charge,
        )

    def get_stripe_product_id(self, tier: PricingTier | None = None) -> str:
        # Get pricing from tier or default
        monthly_charge = self.get_active_monthly_charge(tier)

        # Build product name - include tier info if applicable
        if tier is not None:
            product_name = f"{self.title} - {tier.label}"
        else:
            product_name = self.title

        for product in stripe.Product.list(expand=["data.default_price"]).data:
            if (
                product.default_price
                and product.default_price.unit_amount == monthly_charge * 100
                and product.name == product_name
            ):  # cents
                return product.id

        product = stripe.Product.create(
            name=product_name,
            description=self.description,
            default_price_data={
                "currency": "usd",
                "unit_amount": monthly_charge * 100,
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
