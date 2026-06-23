import base64
import json

import itsdangerous
from fastapi.testclient import TestClient

from app_users.models import AppUser
from daras_ai_v2 import settings
from server import app
from workspaces.models import Workspace
from workspaces.widgets import SESSION_SELECTED_WORKSPACE


def _read_session(client: TestClient) -> dict:
    """Decode the signed session cookie the way Starlette's SessionMiddleware does."""
    cookie = client.cookies.get("session")
    if not cookie:
        return {}
    signer = itsdangerous.TimestampSigner(str(settings.SECRET_KEY))
    data = signer.unsign(cookie, max_age=14 * 24 * 60 * 60)
    return json.loads(base64.b64decode(data))


def test_switch_workspace_route_sets_session_and_redirects(
    transactional_db, force_authentication: AppUser
):
    user = force_authentication
    target = Workspace(name="Team A", created_by=user)
    target.create_with_owner()

    client = TestClient(app)
    r = client.get(
        f"/workspaces/switch/{target.id}/?next=/explore/", follow_redirects=False
    )

    assert r.status_code in (302, 303, 307), r.text
    assert r.headers["location"] == "/explore/"
    assert _read_session(client)[SESSION_SELECTED_WORKSPACE] == target.id


def test_switch_workspace_route_rejects_non_member(
    transactional_db, force_authentication: AppUser
):
    other = AppUser.objects.create(uid="other_user", is_anonymous=False)
    foreign = Workspace(name="Foreign", created_by=other)
    foreign.create_with_owner()

    client = TestClient(app)
    r = client.get(f"/workspaces/switch/{foreign.id}/", follow_redirects=False)

    assert r.status_code == 403, r.text
    assert _read_session(client).get(SESSION_SELECTED_WORKSPACE) != foreign.id
