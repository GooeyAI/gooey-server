from gooey_gui.core.state import set_session_state
from workspaces.models import Workspace
from workspaces.widgets import (
    SESSION_SELECTED_WORKSPACE,
    SWITCH_WORKSPACE_KEY,
    get_current_workspace,
    handle_workspace_switch,
)


def test_get_current_workspace_refreshes_cached_memberships(
    transactional_db, force_authentication
):
    user = force_authentication
    personal_workspace = user.get_or_create_personal_workspace()[0]
    assert user.cached_workspaces == [personal_workspace]
    team_workspace = Workspace(name="Team", created_by=user)
    team_workspace.create_with_owner()
    session = {SESSION_SELECTED_WORKSPACE: team_workspace.id}

    workspace = get_current_workspace(user, session)

    assert workspace == team_workspace


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
