import gooey_gui as gui


def sidebar_layout(*, key: str, session, disabled: bool = False):
    default_open_key = key + ":default-open"
    default_open = persist_toggle_state(default_open_key, session=session)

    gui.session_state.setdefault(key, default_open)
    with gui.component(
        "Sidebar", name=key, disabled=disabled, defaultOpen=default_open
    ):
        return gui.div(), gui.div()


def persist_toggle_state(key: str, *, session, default=None):
    try:
        value = session[key] = gui.session_state[key]
    except KeyError:
        value = session.get(key, default)
    return value
