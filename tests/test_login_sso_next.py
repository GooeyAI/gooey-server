from starlette.testclient import TestClient

from server import app

client = TestClient(app)


def test_login_options_sso_link_encodes_next(db_fixtures):
    r = client.get("/login/?next=/copilot/integrations")
    assert r.is_success, r.text
    assert 'href="/login/sso/?next=%2Fcopilot%2Fintegrations"' in r.text


def test_login_sso_return_link_encodes_next(db_fixtures):
    r = client.get("/login/sso/?next=/copilot/integrations")
    assert r.is_success, r.text
    assert 'href="/login/?next=%2Fcopilot%2Fintegrations"' in r.text
