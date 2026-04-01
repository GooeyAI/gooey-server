from __future__ import annotations

import typing
from enum import Enum
from textwrap import dedent
from typing import Any

import stripe

from daras_ai_v2 import paypal, settings
from .utils import make_stripe_recurring_plan, make_paypal_recurring_plan

if typing.TYPE_CHECKING:
    from payments.models import SeatType, Subscription


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
    footer: str = ""
    deprecated: bool = False
    contact_us_link: str | None = None  # For Special/Enterprise plans

    pricing_title: str | None = None
    pricing_caption: str | None = None

    def get_pricing_title(
        self, *, seat_type: SeatType | None = None, seat_count: int | None = None
    ) -> str:
        if self.pricing_title is not None:
            return self.pricing_title

        if seat_type:
            total_monthly_charge = seat_type.monthly_charge * (seat_count or 1)
        else:
            total_monthly_charge = self.monthly_charge

        return f"${total_monthly_charge}/month"

    def get_pricing_caption(self) -> str:
        return self.pricing_caption or ""

    def get_active_credits(
        self,
        seat_type: typing.Optional["SeatType"] = None,
        seat_count: int = 1,
    ) -> int:
        if seat_type:
            return (seat_type.monthly_credit_limit or 0) * seat_count
        return self.credits

    def get_active_monthly_charge(
        self,
        seat_type: typing.Optional["SeatType"] = None,
        seat_count: int = 1,
    ) -> int:
        if seat_type:
            return seat_type.monthly_charge * seat_count
        return self.monthly_charge


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
              <li>Impact and usage <a href="https://docs.gooey.ai/ai-agent/conversation-analysis">dashboards</a></li>
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

    PRO = PricingPlanData(
        db_value=8,
        key="pro_2026",
        title="Pro",
        description="More for power users",
        monthly_charge=25,
        credits=2_000,
        long_description=dedent(
            """
            #### Everything in Free +
            <ul class="text-muted">
              <li>Private Workflows</li>
              <li>Access to frontier video & animation models</li>
              <li>Increased file upload limit</li>
              <li>Higher rate limits</li>
              <li>Execute any code via JS / Python <a href="/functions/">functions</a></li>
              <li>SOC2 Type II + GDPR Compliance</li>
              <li><a href="https://docs.gooey.ai/api-reference/getting-started">API access</a> to every workflow</li>
              <li>No model training</li>
            </ul>
            """
        ),
        footer="""
        <ul class="text-muted">
          <li>Commercial license for images, QR Codes, and videos</li>
          <li>Premium Support via dedicated Discord Channel</li>
        </ul>
        """,
    )

    TEAM = PricingPlanData(
        db_value=9,
        key="team_2025",
        title="Team",
        description="Predictable pricing per seat.",
        monthly_charge=40,
        credits=2_500,
        long_description=dedent(
            """
            #### All Pro Features +
            <ul class="text-muted">
              <li>Private Team Workspace</li>
              <li>Central billing and administration</li>
              <li>HIPAA, SOC2 Type II, and GDPR compliance</li>
              <li>Integrate with Google, M365, Salesforce, Notion + 100s of others</li>
              <li>API Secrets to securely access any system (Researcher & above)</li>
              <li>Bring your own WhatsApp number</li>
              <li>Embed copilots in your own App</li>
              <li>Impact and usage <a href="https://docs.gooey.ai/ai-agent/conversation-analysis">dashboards</a></li>
              <li>Role Based Management</li>
              <li>Centralized billing</li>
              <li>Version History on Workflows</li>
              <li>Use-case specific, Workflow <a href="https://docs.gooey.ai/tools/evaluations/understanding-bulk-runner-and-evaluation">Evaluation</a> to optimize model and component selection.</li>
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
    )

    ENTERPRISE = PricingPlanData(
        db_value=6,
        key="enterprise",
        title="Enterprise",
        description="Pooled Usage. For organizations ready for transformation with Gooey.AI as the foundation of their AI strategy.",
        monthly_charge=0,
        credits=999_999,
        pricing_title="Custom",
        pricing_caption="Typically $25,000 - $500,000 annually",
        long_description=dedent(
            """
            #### All Team Features +
            <ul class="text-muted">
              <li>Pooled Credits, Submission Rates and Concurrency</li>
              <li>Single sign-on (SSO) &amp; Oauth login</li>
              <li>Zero Data Retention</li>
              <li>Unlimited Workspaces for private collaboration among teams and clients</li>
              <li>Strategic AI consulting including:
                <ul>
                  <li>Rock-bottom, full-transparency, no mark-up token pricing</li>
                  <li>Ongoing cost optimization + evals across all AI model providers</li>
                  <li>Tailored onboarding and training</li>
                </ul>
              </li>
              <li>Bespoke Workflows &amp; features</li>
              <li>Dedicated numbers for WhatsApp, Voice + SMS AI Agents</li>
              <li>Impact + ROI dashboards for your org based on industry best practices</li>
              <li>Export usage to your own BI platforms</li>
              <li>Integrations with your internal systems</li>
              <li>Host + Integrate your fine-tuned model in Gooey.AI infra</li>
              <li>Use your own keys for OpenAI, Azure, and others</li>
              <li>On-prem deployments</li>
              <li>Custom inference queues and rate limits</li>
            </ul>
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

        for plan in cls:
            if not plan.supports_stripe():
                continue

            expected_price = plan.monthly_charge * 100

            if product.name == plan.title and (
                product_price is None or product_price == expected_price
            ):
                return plan
            if product.name.startswith(f"{plan.title} - ") and (
                product_price is None or product_price >= expected_price
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

    # Stripe

    def supports_stripe(self) -> bool:
        return bool(self.monthly_charge)

    def get_stripe_line_item(
        self, *, seat_type: SeatType | None = None, seat_count: int = 1
    ) -> dict[str, Any]:
        if not self.supports_stripe():
            raise ValueError(f"Can't bill {self.title} via Stripe")

        if self == PricingPlan.TEAM and seat_type:
            return {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": seat_type.monthly_charge * 100,
                    "product": self.get_stripe_product_id(
                        product_name=f"{self.title} - {seat_type.name} Seat",
                        seat_type=seat_type,
                    ),
                    "recurring": {"interval": "month"},
                },
                "quantity": seat_count,
            }

        credits = self.get_active_credits(seat_type=seat_type, seat_count=seat_count)
        monthly_charge = self.get_active_monthly_charge(
            seat_type=seat_type, seat_count=seat_count
        )

        if self.key in STRIPE_PRODUCT_NAMES:
            # via product_name
            return make_stripe_recurring_plan(
                product_name=STRIPE_PRODUCT_NAMES[self.key],
                credits=credits,
                amount=monthly_charge,
            )
        else:
            return make_stripe_recurring_plan(
                product_id=self.get_stripe_product_id(),
                credits=credits,
                amount=monthly_charge,
            )

    def get_stripe_product_id(
        self,
        *,
        product_name: str | None = None,
        seat_type: SeatType | None = None,
    ) -> str:
        monthly_charge = self.get_active_monthly_charge(seat_type=seat_type)
        product_name = product_name or self.title

        metadata = {settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD: self.key}
        if seat_type:
            metadata[settings.STRIPE_ITEM_SEAT_TYPE_METADATA_FIELD] = seat_type.key

        for product in stripe.Product.list(expand=["data.default_price"]).data:
            if (
                product.default_price
                and product.default_price.unit_amount == monthly_charge * 100
                and product.metadata == metadata
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
            metadata=metadata,
        )
        return product.id

    # PayPal

    def supports_paypal(self) -> bool:
        return bool(self.monthly_charge)

    def get_paypal_plan(self) -> dict[str, Any]:
        if not self.supports_paypal():
            raise ValueError(f"Can't bill {self.title} via PayPal")

        return make_paypal_recurring_plan(
            plan_id=self.get_paypal_plan_id(),
            credits=self.credits,
            amount=self.monthly_charge,
        )

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
