from gooey_gui.core.state import set_session_state
from workspaces.widgets import (
    SESSION_SELECTED_WORKSPACE,
    SWITCH_WORKSPACE_KEY,
    handle_workspace_switch,
)


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
