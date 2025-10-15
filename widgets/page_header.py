import typing
from bots.models.workflow import Workflow
from daras_ai_v2.fastapi_tricks import get_route_path
import gooey_gui as gui
from daras_ai_v2 import icons, settings
from workspaces.widgets import global_workspace_selector
from widgets.workflow_search import SearchFilters, render_search_bar_with_redirect
from starlette.requests import Request

def render_header_link_as_btn(
    url: str, label: str, icon: str | None = None, is_selected: bool = False
):
    classes = "p-2 bg-hover-light cursor-pointer rounded"
    if is_selected:
        classes += " bg-light"

    with (
        gui.link(to=url, className="text-decoration-none"),
        gui.div(className=classes),
    ):
        gui.html(
            f"{icon} {label}" if icon else label,
        )


JS_SHOW_MOBILE_SEARCH = """
event.preventDefault();
const mobileSearchContainer = document.querySelector("#mobile_search_container");
mobileSearchContainer.classList.add(
    "d-flex", "position-absolute", "top-0", "start-0", "bottom-0", "end-0"
)
document.querySelector('#global_search_bar').focus();
"""

JS_HIDE_MOBILE_SEARCH = """
event.preventDefault();
const mobileSearchContainer = document.querySelector("#mobile_search_container");
mobileSearchContainer.classList.remove(
    "d-flex", "position-absolute", "top-0", "start-0", "bottom-0", "end-0"
);
"""


def render_header_search_bar(request: Request, search_filters: SearchFilters):
    with gui.div(
        className="d-flex d-md-none justify-content-end",
    ):
        gui.button(
            icons.search,
            type="tertiary",
            className="m-0",
            onClick=JS_SHOW_MOBILE_SEARCH,
        )

    with (
        gui.styled("@media (min-width: 768px) { & { position: static !important; } }"),
        gui.div(
            className="d-md-flex flex-grow-1 justify-content-end align-items-center bg-white top-0 left-0",
            style={"display": "none", "zIndex": "10"},
            id="mobile_search_container",
        ),
    ):
        render_search_bar_with_redirect(
            request=request,
            search_filters=search_filters or SearchFilters(),
        )
        gui.button(
            "Cancel",
            type="tertiary",
            className="d-md-none fs-6 m-0 ms-1 p-1",
            onClick=JS_HIDE_MOBILE_SEARCH,
        )


def render_page_header(
    request: Request,
    search_filters: typing.Optional[SearchFilters] = None,
    show_search_bar: bool = True,
    workflow: typing.Optional[Workflow] = None,
):
    from routers.root import anonymous_login_container
    from routers.account import explore_in_current_workspace

    workflow_title = workflow.label
    context = {"request": request, "block_incognito": True}
    with (
        gui.tag("nav", className="header"),
        gui.div(className="navbar navbar-expand-xl bg-transparent p-0 m-0"),
        gui.div(
            className="w-100 d-flex gap-2 py-2 px-3 border-bottom",
        ),
    ):
        # left-block-with-logo-and-links
        with gui.div(className="d-flex align-items-center"):
            with (
                gui.div(className="d-md-block"),
                gui.tag("a", href="/"),
            ):
                gui.tag(
                    "img",
                    src=settings.GOOEY_LOGO_RECT,
                    width="300",
                    height="142",
                    className="img-fluid logo d-none d-sm-block",
                )
                gui.tag(
                    "img",
                    src=settings.GOOEY_LOGO_RECT,
                    width="145",
                    height="40",
                    className="img-fluid logo d-sm-none",
                )

        # center-links-wrapper
        with (
            gui.div(
                className="d-none d-lg-flex justify-content-center align-items-center gap-2 mt-1 ps-2",
                style=dict(
                    fontSize="14px",
                ),
            ),
        ):
            if workflow_title:
                with gui.tooltip("See Examples"):
                    with gui.styled(
                        "& { letter-spacing: 0.05em; text-transform: uppercase; font-weight: bold; }"
                    ):
                        render_header_link_as_btn(
                            url=f"/{workflow.short_slug}/examples",
                            label=workflow_title,
                            icon=settings.HEADER_ICONS.get(f"/{workflow_title}"),
                            is_selected=True,
                        )

            render_header_link_as_btn(
                url=settings.EXPLORE_URL,
                label="Explore",
                icon=settings.HEADER_ICONS.get(settings.EXPLORE_URL),
                is_selected=False,
            )
            if request.user and not request.user.is_anonymous:
                render_header_link_as_btn(
                    url=get_route_path(explore_in_current_workspace),
                    label="Saved",
                    icon=icons.save,
                    is_selected=False,
                )

        # right-block-with-workspace-selector-and-search-bar
        with gui.div(
            className="d-flex gap-2 justify-content-end flex-wrap align-items-center flex-grow-1"
        ):
            if show_search_bar:
                render_header_search_bar(request, search_filters)

            if request.user and not request.user.is_anonymous:
                current_workspace = global_workspace_selector(
                    request.user, request.session
                )
            else:
                current_workspace = None
                anonymous_login_container(request, context)

    return current_workspace
