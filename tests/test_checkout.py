import pytest
from fastapi.testclient import TestClient

from app_users.models import AppUser
from daras_ai_v2 import settings
from daras_ai_v2.billing import stripe_subscription_checkout_redirect
from gooey_gui import RedirectException
from payments.plans import PricingPlan
from server import app

client = TestClient(app)


@pytest.mark.skipif(not settings.STRIPE_SECRET_KEY, reason="No stripe secret")
@pytest.mark.parametrize("plan", PricingPlan)
def test_create_checkout_session(
    plan: PricingPlan, transactional_db, force_authentication: AppUser
):
    if not plan.supports_stripe():
        return

    with pytest.raises(RedirectException):
        stripe_subscription_checkout_redirect(force_authentication, plan)
