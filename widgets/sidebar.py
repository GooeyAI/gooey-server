import gooey_gui as gui
from gooey_gui.types.sidebar_props import SidebarProps


def sidebar_layout(
    *,
    key: str,
    session,
    disabled: bool = False,
    client_only: bool = False,
    storage_key: str | None = None,
):
    default_open_key = key + ":default-open"
    default_open = persist_toggle_state(
        default_open_key, session=session, default=False
    )

    gui.session_state.setdefault(key, default_open)
    with gui.model_component(
        SidebarProps(
            name=key,
            disabled=disabled,
            default_open=default_open,
            client_only=client_only,
            storage_key=storage_key,
        )
    ):
        return gui.div(), gui.div()


def persist_toggle_state(key: str, *, session, default=None):
    try:
        value = session[key] = gui.session_state[key]
    except KeyError:
        value = session.get(key, default)
    return value
