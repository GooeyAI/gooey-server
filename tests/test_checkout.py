import pytest
from fastapi.testclient import TestClient

from routers.billing import available_subscriptions
from server import app

client = TestClient(app)


@pytest.mark.parametrize("subscription", available_subscriptions.keys())
def test_create_checkout_session(
    subscription: str, transactional_db, force_authentication
):
    form_data = {"lookup_key": subscription}
    if subscription == "addon":
        form_data["quantity"] = 1000
    r = client.post(
        "/__/stripe/create-checkout-session",
        data=form_data,
    )
    assert r.ok, r.content
