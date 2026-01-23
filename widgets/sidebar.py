import gooey_gui as gui


def sidebar_layout(*, key: str, session, disabled: bool = False):
    default_open_key = key + ":default-open"
    try:
        default_open = session[default_open_key] = gui.session_state[default_open_key]
    except KeyError:
        default_open = session.get(default_open_key)

    sidebar = gui.RenderTreeNode(
        name="sidebar",
        props=dict(
            name=key,
            disabled=disabled,
            defaultOpen=default_open,
        ),
    )
    sidebar.mount()
    with gui.NestingCtx(sidebar):
        return gui.div(), gui.div()
