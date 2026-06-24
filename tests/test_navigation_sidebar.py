from starlette.authentication import AuthCredentials
from starlette.requests import Request

from app_users.models import AppUser
from widgets.navigation_sidebar import build_props
from workspaces.widgets import SESSION_SELECTED_WORKSPACE


def _make_request(user: AppUser | None, session: dict, path: str = "/home/") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
        "session": session,
        "user": user,
        "auth": AuthCredentials(["authenticated"] if user else []),
    }
    return Request(scope)


def test_build_props_populates_identity(
    transactional_db, force_authentication: AppUser
):
    user = force_authentication
    ws = user.cached_workspaces[0]
    req = _make_request(user, {SESSION_SELECTED_WORKSPACE: ws.id})

    props = build_props(req)

    assert props.user is not None
    assert props.user.initial
    assert props.current_workspace is not None
    assert props.current_workspace.id == ws.id
    assert any(w.is_current for w in props.workspaces)
    assert props.logout_href
    assert "{workspace_id}" in props.switch_workspace_href
    # full primary nav for logged-in users
    assert {item.key for item in props.nav_items} == {"home", "explore", "saved"}
    labels = {m.label for m in props.menu_links}
    assert {"Profile", "Billing", "Members"} <= labels


def test_build_props_anonymous(transactional_db):
    props = build_props(_make_request(None, {}))

    assert props.user is None
    assert props.current_workspace is None
    assert props.workspaces == []
    assert props.switch_workspace_href == ""
    # reduced rail: only Explore as a primary item
    assert [item.key for item in props.nav_items] == ["explore"]
    # public links only — no account links for anonymous users
    labels = {m.label for m in props.menu_links}
    assert labels
    assert not ({"Profile", "Billing", "Members"} & labels)
    # Sign In points at the login flow with a return path
    assert "/login" in props.login_href
