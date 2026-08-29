from types import SimpleNamespace

from starlette.requests import Request

from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_route_path
from gooey_gui.core.state import set_session_state
from widgets import navigation_sidebar
from workspaces.models import Workspace
from workspaces.widgets import (
    SESSION_SELECTED_WORKSPACE,
    SWITCH_WORKSPACE_KEY,
    get_current_workspace,
    handle_workspace_switch,
)


def test_navigation_sidebar_logo_links_to_app_base_url(monkeypatch):
    rendered_components = []
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/explore/",
            "query_string": b"",
            "headers": [],
            "scheme": "https",
            "server": ("testserver", 443),
            "client": ("testclient", 123),
            "root_path": "",
            "user": None,
            "session": {},
        }
    )
    monkeypatch.setattr(
        navigation_sidebar.gui, "model_component", rendered_components.append
    )

    navigation_sidebar.render(request)

    assert rendered_components[0].logo_href == settings.APP_BASE_URL


def test_account_menu_follows_the_workspace_kind():
    """A personal workspace's settings are its owner's profile, an org's are its people.
    `profile_route` and `members_route` redirect to one another, so offering the wrong one
    would bounce the reader straight back."""
    from routers.account import members_route, profile_route

    personal = _account_menu(is_personal=True)
    org = _account_menu(is_personal=False)

    assert personal["Profile"] == get_route_path(profile_route)
    assert "Members" not in personal
    assert org["Members"] == get_route_path(members_route)
    assert "Profile" not in org


def test_account_menu_api_goes_to_the_workspaces_own_keys():
    """`/api/` is reference material written for a visitor. A signed-in reader clicking API
    from their workspace means their keys, so the docs stay reachable under Docs alone."""
    from routers.account import api_keys_route

    for is_personal in (True, False):
        assert _account_menu(is_personal=is_personal)["API"] == get_route_path(
            api_keys_route
        )

    anonymous = navigation_sidebar._load_menu_links(True, None)
    assert {link.label: link.href for link in anonymous}["API"] == settings.API_URL


def _account_menu(*, is_personal: bool) -> dict[str, str]:
    """The signed-in menu as `{label: href}`. Only `is_personal` is read off the workspace."""
    links = navigation_sidebar._load_menu_links(
        False, SimpleNamespace(is_personal=is_personal)
    )
    return {link.label: link.href for link in links}


def test_sidebar_refreshes_cached_workspace_memberships(
    transactional_db, force_authentication
):
    user = force_authentication
    personal_workspace = user.get_or_create_personal_workspace()[0]
    assert user.cached_workspaces == [personal_workspace]
    team_workspace = Workspace(name="Team", created_by=user)
    team_workspace.create_with_owner()
    session = {SESSION_SELECTED_WORKSPACE: team_workspace.id}

    navigation_sidebar._refresh_workspace_cache(user)
    workspace = get_current_workspace(user, session)

    assert workspace == team_workspace


def test_get_current_workspace_reuses_cached_memberships(
    transactional_db, force_authentication, django_assert_num_queries
):
    user = force_authentication
    workspace = user.get_or_create_personal_workspace()[0]
    session = {SESSION_SELECTED_WORKSPACE: workspace.id}
    get_current_workspace(user, session)

    with django_assert_num_queries(0):
        assert get_current_workspace(user, session) == workspace


def test_handle_workspace_switch_ignores_invalid_workspace_id():
    session = {}
    set_session_state({SWITCH_WORKSPACE_KEY: "not-a-workspace"})

    handle_workspace_switch(session)

    assert SESSION_SELECTED_WORKSPACE not in session


def test_handle_workspace_switch_stores_parsed_workspace_id():
    session = {}
    set_session_state({SWITCH_WORKSPACE_KEY: "42"})

    handle_workspace_switch(session)

    assert session[SESSION_SELECTED_WORKSPACE] == 42
