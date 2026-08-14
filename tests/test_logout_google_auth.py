from pathlib import Path

from starlette.testclient import TestClient

import pytest
from daras_ai_v2 import settings
from server import app


client = TestClient(app)


def test_logout_clears_session_and_returns_client_cleanup_page():
    r = client.get("/logout/", follow_redirects=False)
    assert r.status_code == 200, r.text
    assert r.headers.get("cache-control") == "no-store"
    assert "sessionStorage" in r.text
    assert "g_state" in r.text
    assert "window.location.replace" in r.text
    assert 'window.location.replace("/")' in r.text or "location.replace('/')" in r.text


def test_logout_honors_safe_next():
    r = client.get("/logout/?next=/explore/", follow_redirects=False)
    assert r.status_code == 200, r.text
    assert "/explore/" in r.text


def test_logout_rejects_open_redirect():
    r = client.get(
        "/logout/?next=https://evil.example/phish",
        follow_redirects=False,
    )
    assert r.status_code == 200, r.text
    assert "evil.example" not in r.text
    assert 'window.location.replace("/")' in r.text or "location.replace('/')" in r.text


@pytest.mark.skipif(
    not settings.ENABLE_FIREBASE_AUTH, reason="Firebase auth is not enabled"
)
def test_login_page_does_not_double_init_gsi():
    r = client.get("/login/")
    assert r.is_success, r.text
    # Header GSI (google_one_tap_button.html) must not load on /login/ —
    # FirebaseUI owns the Google button there. Two GSI initialize() calls
    # reset the client and produce accounts.google.com 400s after logout.
    assert "g_id_signin_desktop" not in r.text
    assert "accounts.google.com/gsi/client" not in r.text
    assert "/static/js/login_options.js" in r.text


def test_login_options_uses_firebase_popup_not_gsi_client_id():
    text = Path("static/js/login_options.js").read_text()
    assert "clientId:" not in text
    assert 'prompt: "select_account"' in text
