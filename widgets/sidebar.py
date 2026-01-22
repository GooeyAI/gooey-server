import gooey_gui as gui


def sidebar_layout(*, key: str, session, disabled: bool = False):
    default_open_key = key + ":default-open"
    try:
        default_open = session[default_open_key] = gui.session_state[default_open_key]
    except KeyError:
        default_open = session.get(default_open_key)

    page_content = gui.RenderTreeNode(name="page-content")
    sidebar = gui.RenderTreeNode(
        name="sidebar",
        props=dict(
            name=key,
            page_content=page_content,
            disabled=disabled,
            defaultOpen=default_open,
        ),
    )
    sidebar.mount()
    return gui.NestingCtx(sidebar), gui.NestingCtx(page_content)
