import typing
from copy import copy

import gooey_gui as gui
from starlette.requests import Request

from daras_ai.text_format import format_number_with_suffix
from daras_ai_v2 import icons
from daras_ai_v2.all_pages import all_home_pages_by_category
from daras_ai_v2.base import BasePage
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.meta_content import raw_build_meta_tags
from widgets.workflow_search import (
    SearchFilters,
    render_search_bar_with_redirect,
    render_search_filters,
    render_search_results,
)

META_TITLE = "Explore AI Workflows"
META_DESCRIPTION = "Find, fork and run your field’s favorite AI recipes on Gooey.AI"

TITLE = "Explore"
DESCRIPTION = "DISCOVER YOUR FIELD’S FAVORITE AI WORKFLOWS"


def build_meta_tags(url: str, search_filters: SearchFilters | None):
    from daras_ai_v2.all_pages import normalize_slug, page_slug_map

    if not search_filters:
        search_filters = SearchFilters()

    match search_filters.search, search_filters.workflow:
        case "", "":
            title = META_TITLE
        case query, "":
            title = f"{query} AI Workflows"
        case query, workflow:
            page = page_slug_map.get(normalize_slug(workflow))
            if page:
                title = f"{query} {page.workflow.short_title} Workflows".lstrip()
            else:
                title = META_TITLE

    title += " | Gooey.AI"

    return raw_build_meta_tags(
        url=url,
        title=title,
        description=META_DESCRIPTION,
    )


def render(request: Request, search_filters: SearchFilters | None):
    with gui.div(className="my-4"):
        # note: using css instead of `if not search_filters: ...` stops re-render
        # of the search bar. this preserves focus/blur between query-param redirects
        gui.caption(
            DESCRIPTION,
            className="text-muted m-0",
            style={"display": "none"} if search_filters else None,
        )

        search_filters = search_filters or SearchFilters()
        render_search_bar_with_redirect(
            request=request,
            search_filters=search_filters,
            max_width="600px",
        )
        with gui.div(className="mt-3"):
            new_filters = render_search_filters(
                current_user=request.user, search_filters=copy(search_filters)
            )
            if new_filters != search_filters:
                # if the search bar value has changed, redirect to the new search page
                raise gui.QueryParamsRedirectException(
                    new_filters.model_dump(exclude_defaults=True)
                )

    if search_filters:
        with gui.div(className="my-4"):
            render_search_results(request.user, search_filters)
            return

    for category, pages in all_home_pages_by_category.items():
        gui.write("---")
        if category != "Featured":
            section_heading(category)
        if category == "Images" or category == "Featured":
            grid_layout(3, pages, _render_as_featured, separator=False)
        else:
            grid_layout(2, pages, _render_non_featured, separator=False)


def heading(
    title: str, description: str, margin_top: str = "2rem", margin_bottom: str = "2rem"
):
    with gui.div(style={"marginTop": margin_top, "marginBottom": margin_bottom}):
        with gui.tag(
            "p",
            style={"marginTop": "0rem", "marginBottom": "0rem"},
            className="text-muted",
        ):
            gui.html(description.upper())
        with gui.tag(
            "h1",
            style={"marginTop": "0px", "marginBottom": "0px", "fontWeight": "500"},
        ):
            gui.html(title)


def section_heading(title: str, margin_top: str = "1rem", margin_bottom: str = "1rem"):
    with gui.tag(
        "h5",
        style={
            "fontWeight": "600",
            "marginTop": margin_top,
            "marginBottom": margin_bottom,
        },
    ):
        with gui.tag("span", style={"backgroundColor": "#A5FFEE"}):
            gui.html(title.upper())


def render_image(page: BasePage):
    gui.image(
        page.get_explore_image(),
        href=page.app_url(),
        style={"borderRadius": 5},
    )


def _render_as_featured(page_cls: typing.Type[BasePage]):
    page = page_cls()
    render_image(page)
    render_description(page)


def _render_non_featured(page_cls: typing.Type[BasePage]):
    page = page_cls()
    col1, col2 = gui.columns([1, 2])
    with col1:
        render_image(page)
    with col2:
        render_description(page)


def render_description(page: BasePage):
    with gui.link(to=page.app_url()):
        gui.markdown(f"#### {page.get_recipe_title()}")

    root_pr = page.get_root_pr()
    with gui.div(className="mb-3"):
        gui.write(root_pr.notes, line_clamp=4)

    if root_pr.run_count >= 50:
        run_count = format_number_with_suffix(root_pr.run_count)
        with gui.div(className="d-flex align-items-center"):
            gui.caption(
                f"{icons.run} {run_count} runs",
                unsafe_allow_html=True,
                className="text-muted",
                style={"fontSize": "0.9rem"},
            )
