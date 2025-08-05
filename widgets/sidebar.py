import gooey_gui as gui
from daras_ai_v2 import settings
from textwrap import dedent
from daras_ai_v2 import icons


class SidebarRef:
    def __init__(self, key: str, is_open: bool = True, is_mobile_open: bool = False):
        self.key = key
        self.is_open = is_open
        self.is_mobile_open = is_mobile_open

    def set_open(self, value: bool):
        self.is_open = gui.session_state[self.key] = value

    def set_mobile_open(self, value: bool):
        self.is_mobile_open = gui.session_state[self.mobile_key] = value
        self.set_open(value)

    @property
    def mobile_key(self):
        return self.key + ":mobile"

    @property
    def toggle_btn_key(self):
        return self.key + ":toggle"

    @property
    def close_btn_key(self):
        return self.key + ":close"

    @property
    def open_btn_key(self):
        return self.key + ":open"


def use_sidebar(key: str, default_open: bool = True) -> SidebarRef:
    """Create or get a sidebar reference with state management."""
    ref = SidebarRef(
        key=key,
        is_open=bool(gui.session_state.get(key, default_open)),
        is_mobile_open=bool(gui.session_state.get(key + ":mobile", False)),
    )

    return ref


def sidebar_list_item(icon, title, is_sidebar_open):
    with (
        gui.styled(
            """
            & i {
                font-size: 1.2rem;
                max-width: 18px;
            }
        """
        ),
        gui.div(className="d-inline-block me-4"),
    ):
        gui.html(icon, className="me-2")
    if is_sidebar_open:
        gui.html(title)


def sidebar_item_list(is_sidebar_open):
    for i, (url, label, icon) in enumerate(settings.SIDEBAR_LINKS):
        if not is_sidebar_open and i >= 1:
            break
        with gui.tag("a", href=url, className="text-decoration-none d-flex"):
            if icon:
                with gui.div(
                    className="d-inline-block me-3",
                    style={"height": "24px"},
                ):
                    sidebar_list_item(icon, label, is_sidebar_open)
            else:
                with gui.div(
                    className="d-inline-block me-3 small",
                    style={"width": "24px"},
                ):
                    gui.html("&nbsp;")
                gui.html(label)


def render_default_sidebar():
    is_sidebar_open = gui.session_state.get("main-sidebar", True)
    with gui.div(
        className="d-flex flex-column flex-grow-1 gap-3 px-3 my-3 text-nowrap",
        style={"marginLeft": "4px"},
    ):
        with gui.tag(
            "a",
            href="/saved/",
            className="pe-2 text-decoration-none d-flex",
        ):
            sidebar_list_item(
                "<i class='fa-regular fa-floppy-disk'></i>", "Saved", is_sidebar_open
            )

        sidebar_item_list(is_sidebar_open)


def sidebar_logo_header():
    with gui.div(
        className="d-flex align-items-center justify-content-between d-md-none me-2 w-100 py-2"
    ):
        sidebar_ref = use_sidebar("main-sidebar", default_open=True)
        gui.tag(
            "img",
            src=settings.GOOEY_LOGO_FACE,
            width="44px",
            height="44px",
            className=" logo-face",
        )
        open_mobile_sidebar = gui.button(
            label=icons.sidebar_flip,
            className="m-0",
            unsafe_allow_html=True,
            type="tertiary",
        )
        if open_mobile_sidebar:
            print(sidebar_ref.set_mobile_open, ">>>")
            sidebar_ref.set_mobile_open(True)
            raise gui.RerunException()


def sidebar_layout(sidebar_ref: SidebarRef):
    is_mobile_open = sidebar_ref.is_mobile_open
    sidebar_funtion_classes = (
        "gooey-sidebar-open" if sidebar_ref.is_open else "gooey-sidebar-closed"
    )
    side_bar_styles = dedent(
        """
            & .gooey-sidebar {
                transition: width 0.2s cubic-bezier(0.4, 0, 0.2, 1), min-width 0.2s cubic-bezier(0.4, 0, 0.2, 1), max-width 0.2s cubic-bezier(0.4, 0, 0.2, 1);
                background-color: #f9f9f9;
                position: sticky;
                top: 0;
                left: 0;
                bottom: 0;
                z-index: 999;
            }
            & .gooey-sidebar-open {
                min-width: 250px;
                width: 250px;
                max-width: 250px;
            }
            & .gooey-sidebar-closed {
                min-width: 60px;
                width: 60px;
                max-width: 60px;
            }

            @media (max-width: 767px) {
                & .gooey-sidebar-open {
                    position: fixed;
                    min-width: 100vw;
                    width: 100vw;
                    max-width: 100vw;
                    z-index: 2000;
                }
                & .gooey-sidebar-closed {
                    position: fixed;
                    min-width: 0px;
                    width: 0px;
                    max-width: 0px;
                    overflow: hidden;
                }
            }
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
            className="d-flex w-100 h-100 position-relative", style={"height": "100dvh"}
        ),
    ):
        sidebar_content_placeholder = gui.div(
            className=f"d-flex flex-column flex-grow-1 gooey-sidebar {sidebar_funtion_classes}",
            style={"height": "100dvh"},
        )
        pane_content_placeholder = gui.div(className="d-flex flex-grow-1")
        # sidebar content
        sidebar_content_placeholder
        pane_content_placeholder
    return sidebar_content_placeholder, pane_content_placeholder
