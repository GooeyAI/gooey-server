import gooey_ui as gui
from daras_ai.image_input import truncate_text_words
from daras_ai_v2.all_pages import all_home_pages_by_category
from daras_ai_v2.grid_layout_widget import grid_layout


META_TITLE = "Explore AI workflows"
META_DESCRIPTION = "Find, fork and run your field’s favorite AI recipes on Gooey.AI"

TITLE = "Explore"
DESCRIPTION = "DISCOVER YOUR FIELD’S FAVORITE AI WORKFLOWS"


def render():
    def _render(page_cls):
        page = page_cls()
        state = page.recipe_doc_sr().to_dict()

        with gui.link(to=page.app_url()):
            gui.markdown(f"### {page.title}")

        preview = page.preview_description(state)
        if preview:
            gui.write(preview, line_clamp=2)
        else:
            page.render_description()

        page.render_example(state)

    heading(title=TITLE, description=DESCRIPTION)
    for category, pages in all_home_pages_by_category.items():
        gui.write("---")
        section_heading(category)
        grid_layout(3, pages, _render, separator=False)


def heading(
    title: str, description: str, margin_top: str = "2rem", margin_bottom: str = "2rem"
):
    with gui.tag(
        "div", style={"margin-top": margin_top, "margin-bottom": margin_bottom}
    ):
        with gui.tag(
            "p",
            style={"margin-top": "0rem", "margin-bottom": "0rem"},
            className="text-muted",
        ):
            gui.html(description.upper())
        with gui.tag(
            "h1",
            style={"margin-top": "0px", "margin-bottom": "0px", "font-weight": "500"},
        ):
            gui.html(title)


def section_heading(title: str, margin_top: str = "1rem", margin_bottom: str = "1rem"):
    with gui.tag(
        "h5",
        style={
            "font-weight": "600",
            "margin-top": margin_top,
            "margin-bottom": margin_bottom,
        },
    ):
        with gui.tag("span", style={"background-color": "#A5FFEE"}):
            gui.html(title.upper())
