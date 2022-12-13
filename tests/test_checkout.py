import pytest
from fastapi.testclient import TestClient

from auth_backend import force_authentication
from routers.stripe_apis import available_subscriptions
from server import app

client = TestClient(app)


@pytest.mark.parametrize("subscription", available_subscriptions.keys())
def test_create_checkout_session(subscription: str):
    with force_authentication():
        r = client.post(
            "/__/stripe/create-checkout-session",
            data={"lookup_key": subscription},
        )
    assert r.ok, r.content
