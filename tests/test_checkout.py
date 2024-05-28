import pytest
from fastapi.testclient import TestClient

from server import app
from payments.plans import PricingPlan

client = TestClient(app)


@pytest.mark.parametrize("plan", PricingPlan)
def test_create_checkout_session(
    plan: PricingPlan, transactional_db, force_authentication
):
    if not plan.monthly_charge:
        return

    form_data = {"lookup_key": plan.key}
    r = client.post(
        "/__/stripe/create-checkout-session",
        data=form_data,
    )
    assert r.ok, r.content
