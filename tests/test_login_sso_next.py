from starlette.testclient import TestClient

import pytest
from server import app
from daras_ai_v2 import settings


client = TestClient(app)


@pytest.mark.skipif(
    not settings.ENABLE_FIREBASE_AUTH, reason="Firebase auth is not enabled"
)
def test_login_options_sso_link_encodes_next(db_fixtures):
    r = client.get("/login/?next=/copilot/integrations")
    assert r.is_success, r.text
    assert 'href="/login/sso/?next=%2Fcopilot%2Fintegrations"' in r.text


@pytest.mark.skipif(
    not settings.ENABLE_FIREBASE_AUTH, reason="Firebase auth is not enabled"
)
def test_login_sso_return_link_encodes_next(db_fixtures):
    r = client.get("/login/sso/?next=/copilot/integrations")
    assert r.is_success, r.text
    assert 'href="/login/?next=%2Fcopilot%2Fintegrations"' in r.text
