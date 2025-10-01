import gooey_gui as gui
from daras_ai_v2 import settings
from textwrap import dedent
from daras_ai_v2 import icons


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
        self.set_open(value)

    @property
    def mobile_key(self):
        return self.key + ":mobile"


def use_sidebar(key: str, session: dict, default_open: bool = True) -> SidebarRef:
    """Create or get a sidebar reference with state management."""
    import time

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

    ref = SidebarRef(
        key=key,
        session=session,
        is_open=bool(session.get(key, default_open)),
        is_mobile_open=bool(session.get(key + ":mobile", False)),
    )

    return ref


def sidebar_list_item(
    icon, title, is_sidebar_open, url=None, hover_icon=None, current_url=None
):
    is_selected = current_url and url and current_url.startswith(url)
    with (
        gui.styled(
            """
            & a {
                font-size: 1rem;
                text-decoration: none;
            }
            & .sidebar-list-item {
                border-radius: 8px;
                height: 36px;
                width: min-content;
                padding: 6px 10px;
            }
            & .sidebar-list-item-hover-icon {
                display: none;
            }
            & .sidebar-list-item:hover {
                background-color: #f0f0f0;
                .sidebar-list-item-hover-icon {
                    display: block;
                }
            }
            & .sidebar-list-item.selected {
                background-color: #ddd;
            }
            & .sidebar-list-item-title {
                font-size: 0.875rem;
            }
        """
        ),
        gui.div(),
    ):
        link_classes = "d-block sidebar-list-item ms-2"
        if is_sidebar_open:
            link_classes += " d-flex align-items-baseline justify-content-between w-100"
        if is_selected:
            link_classes += " selected"
        with gui.tag(
            "a",
            href=url,
            className=link_classes,
        ):
            with gui.div(className="d-flex align-items-baseline"):
                icon_classes = "d-block sidebar-list-item-icon"
                if is_sidebar_open:
                    icon_classes += " me-2"

                if icon:
                    gui.html(
                        icon,
                        className=icon_classes,
                    )
                if is_sidebar_open:
                    gui.html(title, className="sidebar-list-item-title d-block")

            if hover_icon:
                with gui.div(className="sidebar-list-item-hover-icon"):
                    gui.html(hover_icon, className="text-secondary")


def sidebar_item_list(is_sidebar_open, current_url=None):
    for i, (url, label, icon) in enumerate(settings.SIDEBAR_LINKS):
        if icon:
            with gui.div():
                sidebar_list_item(
                    icon, label, is_sidebar_open, url, icons.arrow_up_right, current_url
                )
        else:
            with gui.div(
                className="d-inline-block me-2 small",
            ):
                gui.html("&nbsp;")
            gui.html(label)


def render_default_sidebar(sidebar_ref: SidebarRef, request=None):
    is_sidebar_open = sidebar_ref.is_open
    current_url = request.url.path if request else None

    with gui.div(
        className=f"d-flex flex-column flex-grow-1 {'pe-3' if is_sidebar_open else ''} my-3 text-nowrap",
    ):
        with gui.div(className="mb-4"):
            sidebar_list_item(
                "<i class='fa-regular fa-floppy-disk'></i>",
                "Saved",
                is_sidebar_open,
                "/account/saved/",
                current_url=current_url,
            )
            sidebar_list_item(
                icons.search,
                "Explore",
                is_sidebar_open,
                "/explore/",
                current_url=current_url,
            )

        if is_sidebar_open:
            sidebar_item_list(is_sidebar_open, current_url)


def sidebar_mobile_header(session: dict):
    with gui.div(
        className="d-flex align-items-center justify-content-between d-md-none me-2 w-100 py-2",
        style={"height": "54px"},
    ):
        sidebar_ref = use_sidebar("main-sidebar", session)
        gui.tag(
            "img",
            src=settings.GOOEY_LOGO_FACE,
            width=settings.SIDEBAR_ICON_SIZE,
            height=settings.SIDEBAR_ICON_SIZE,
            className=" logo-face",
        )
        open_mobile_sidebar = gui.button(
            label=icons.sidebar_flip,
            className="m-0",
            unsafe_allow_html=True,
            type="tertiary",
            style={"padding": "6px 10px"},
        )
        if open_mobile_sidebar:
            sidebar_ref.set_mobile_open(True)
            raise gui.RerunException()


# Sidebar width variables
sidebar_open_width = "245px"
sidebar_closed_width = "53px"
sidebar_mobile_width = "80vw"


def sidebar_layout(sidebar_ref: SidebarRef):
    is_mobile_open = sidebar_ref.is_mobile_open
    sidebar_funtion_classes = (
        "gooey-sidebar-open" if sidebar_ref.is_open else "gooey-sidebar-closed"
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
                transition: width 0.2s cubic-bezier(0.4, 0, 0.2, 1), min-width 0.2s cubic-bezier(0.4, 0, 0.2, 1), max-width 0.2s cubic-bezier(0.4, 0, 0.2, 1);
                background-color: #f9f9f9;
                position: sticky;
                top: 0;
                left: 0;
                bottom: 0;
                z-index: 999;
                border-right: 1px solid #e0e0e0;
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

            @media (max-width: 767px) {{
                & .gooey-sidebar-open {{
                    position: fixed;
                    min-width: {sidebar_mobile_width};
                    width: {sidebar_mobile_width};
                    max-width: {sidebar_mobile_width};
                    z-index: 2000;
                }}
                & .gooey-sidebar-closed {{
                    position: fixed;
                    min-width: 0px;
                    width: 0px;
                    max-width: 0px;
                    overflow: hidden;
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
            className="d-flex w-100 h-100 position-relative sidebar-click-container",
            style={"height": "100dvh"},
            onClick=dedent(
                """
                if (event.target.id === "sidebar-click-container") {
                    document.getElementById("sidebar-hidden-btn").click();
                }
                """
                if not sidebar_ref.is_open
                else ""
            ),
        ),
    ):
        open_sidebar_btn = gui.button(
            label="",
            className="d-none",
            id="sidebar-hidden-btn",
        )
        if open_sidebar_btn:
            sidebar_ref.set_open(True)
            raise gui.RerunException()

        sidebar_content_placeholder = gui.div(
            className=f"d-flex flex-column flex-grow-1 gooey-sidebar {sidebar_funtion_classes}",
            style={"height": "100dvh"},
        )
        pane_content_placeholder = gui.div(className="d-flex flex-grow-1 mw-100")
    return sidebar_content_placeholder, pane_content_placeholder
