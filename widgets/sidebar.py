import gooey_gui as gui
from textwrap import dedent


class SidebarRef:
    def __init__(
        self,
        key: str,
        session: dict,
        is_open: bool = True,
        is_mobile_open: bool = False,
    ):
        self.key = key
        self.session = session
        self.is_open = is_open
        self.is_mobile_open = is_mobile_open

    def set_open(self, value: bool):
        self.is_open = self.session[self.key] = value

    def set_mobile_open(self, value: bool):
        self.is_mobile_open = self.session[self.mobile_key] = value
        # self.set_open(value)

    @property
    def mobile_key(self):
        return self.key + ":mobile"


def use_sidebar(key: str, session: dict, default_open: bool = True) -> SidebarRef:
    """Create or get a sidebar reference with state management."""
    import time

    ## HUGE HACK HERE
    # Check if this is a fresh page load by comparing timestamps
    last_load_time = session.get(f"{key}:last_load_time", 0)
    current_time = time.time()

    # If more than 1 second has passed since last load, consider it a fresh page load
    if current_time - last_load_time > 0.5:
        # Fresh page load - clear mobile state
        mobile_key = key + ":mobile"
        if mobile_key in session:
            del session[mobile_key]

    # Update the last load time
    session[f"{key}:last_load_time"] = current_time

    # set the default open state in session here
    session[key] = bool(session.get(key, default_open))
    ref = SidebarRef(
        key=key,
        session=session,
        is_open=bool(session.get(key, default_open)),
        is_mobile_open=bool(session.get(key + ":mobile", False)),
    )

    return ref

# Sidebar width variables
sidebar_open_width = "340px"
sidebar_closed_width = "0px"
sidebar_mobile_width = "100vw"


def sidebar_layout(sidebar_ref: SidebarRef):
    is_mobile_open = sidebar_ref.is_mobile_open
    sidebar_funtion_classes = (
        "gooey-sidebar-open"
        if sidebar_ref.is_open or sidebar_ref.is_mobile_open
        else "gooey-sidebar-closed"
    )

    side_bar_styles = dedent(
        f"""
            html {{
                /* override margin-left from app.css */
                margin-left: 0 !important;
            }}
            & .gooey-btn {{
                padding: 6px 10px !important;
            }}
            & .gooey-btn:hover {{
                background-color: #f0f0f0 !important;
            }}

            & .gooey-sidebar {{
                background-color: #f9f9f9;
                position: sticky;
                top: 0;
                left: 0;
                bottom: 0;
                z-index: 999;
                border-right: 1px solid #e0e0e0;
                height: 100dvh;
            }}

            & .gooey-sidebar-open {{
                min-width: {sidebar_open_width};
                width: {sidebar_open_width};
                max-width: {sidebar_open_width};
            }}
            & .gooey-sidebar-closed {{
                min-width: {sidebar_closed_width};
                width: {sidebar_closed_width};
                max-width: {sidebar_closed_width};
            }}

            & .gooey-sidebar-closed:hover {{
                cursor: e-resize;
            }}

            @media (max-width: 990px) {{
                & .gooey-sidebar-open {{
                    position: fixed;
                    left: 0;
                    bottom: 0;
                    min-width: {sidebar_mobile_width};
                    width: {sidebar_mobile_width};
                    max-width: {sidebar_mobile_width};
                    z-index: 100;
                    border-left: 1px solid #e0e0e0;
                    border-right: none;
                    height: calc(100dvh); /* 4px for the progress bar */
                    margin-top: auto;
                }}
                & .gooey-sidebar-closed {{
                    position: sticky;
                    right: 0;
                    left: auto;
                    min-width: 0px;
                    width: 0px;
                    max-width: 0px;
                    overflow: visible;
                }}
            }}
        """
    )
    if not is_mobile_open:
        side_bar_styles += dedent(
            """
            @media (max-width: 767px) {
                & .gooey-sidebar-open {
                    display: none !important;
                    position: fixed;
                    max-width: 0px !important;
                }
            }
        """
        )

    with (
        gui.styled(side_bar_styles),
        gui.div(
            className="d-flex w-100 h-100 position-relative",
            style={"height": "100dvh"},
        ),
    ):
        sidebar_content_placeholder = gui.div(
            className=f"d-flex flex-column flex-grow-1 gooey-sidebar {sidebar_funtion_classes}",
        )
        pane_content_placeholder = gui.div(className="d-flex flex-grow-1 mw-100")
    return sidebar_content_placeholder, pane_content_placeholder
