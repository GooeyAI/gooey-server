import pytest
from fastapi.testclient import TestClient

from app_users.models import AppUser
from daras_ai_v2 import settings
from daras_ai_v2.billing import create_stripe_checkout_session
from gooey_ui import RedirectException
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
        create_stripe_checkout_session(force_authentication, plan)
