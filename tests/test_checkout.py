import pytest
from fastapi.testclient import TestClient

from auth_backend import force_authentication
from routers.billing import available_subscriptions
from server import app

client = TestClient(app)


@pytest.mark.parametrize("subscription", available_subscriptions.keys())
def test_create_checkout_session(subscription: str):
    with force_authentication():
        form_data = {"lookup_key": subscription}
        if subscription == "addon":
            form_data["quantity"] = 1000
        r = client.post(
            "/__/stripe/create-checkout-session",
            data=form_data,
        )
    print(r.content)
    assert r.ok
