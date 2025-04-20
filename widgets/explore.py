import typing

import gooey_gui as gui

from app_users.models import AppUser
from daras_ai.text_format import format_number_with_suffix
from daras_ai_v2 import icons
from daras_ai_v2.all_pages import all_home_pages_by_category
from daras_ai_v2.base import BasePage
from daras_ai_v2.grid_layout_widget import grid_layout
from widgets.workflow_search import render_search_bar, render_search_results

META_TITLE = "Explore AI workflows"
META_DESCRIPTION = "Find, fork and run your field’s favorite AI recipes on Gooey.AI"

TITLE = "Explore"
DESCRIPTION = "DISCOVER YOUR FIELD’S FAVORITE AI WORKFLOWS"


def render(user: AppUser | None):
    heading(title=TITLE, description=DESCRIPTION, margin_bottom="1rem")

    search_query = render_search_bar()
    if search_query:
        return render_search_results(search_query, user)

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
    with gui.tag("div", style={"marginTop": margin_top, "marginBottom": margin_bottom}):
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
    # total_runs = page.get_total_runs()
    # render_description(page, state, total_runs)
    render_description(page)


def _render_non_featured(page_cls):
    page = page_cls()
    col1, col2 = gui.columns([1, 2])
    with col1:
        render_image(page)
    with col2:
        # total_runs = page.get_total_runs()
        # render_description(page, state, total_runs)
        render_description(page)


def render_description(page: BasePage):
    with gui.link(to=page.app_url()):
        gui.markdown(f"#### {page.get_recipe_title()}")

    root_pr = page.get_root_pr()
    notes = root_pr.notes or page.preview_description(state=page.sane_defaults)
    with gui.div(className="mb-3"):
        gui.write(notes, line_clamp=4)
    if root_pr.run_count > 1:
        run_count = format_number_with_suffix(root_pr.run_count)
        gui.caption(
            f"{icons.run} {run_count} runs",
            unsafe_allow_html=True,
            style={"fontSize": "0.9rem"},
        )
