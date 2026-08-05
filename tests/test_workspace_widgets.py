from starlette.requests import Request

from daras_ai_v2 import settings
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
