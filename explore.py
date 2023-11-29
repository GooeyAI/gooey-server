import gooey_ui as gui
from daras_ai.image_input import truncate_text_words
from daras_ai_v2.all_pages import all_home_pages_by_category
from daras_ai_v2.grid_layout_widget import grid_layout
import fontawesome as fa


META_TITLE = "Explore AI workflows"
META_DESCRIPTION = "Find, fork and run your field’s favorite AI recipes on Gooey.AI"

TITLE = "Explore"
DESCRIPTION = "DISCOVER YOUR FIELD’S FAVORITE AI WORKFLOWS"


def render():
    def _render_non_featured(page_cls):
        page = page_cls()
        state = page.recipe_doc_sr().to_dict()
        total_runs = page.get_total_runs()

        col1, col2 = gui.columns([1, 2])
        with col1:
            render_image(page, state)

        with col2:
            render_description(page, state)

    def _render_as_featured(page_cls):
        page = page_cls()
        state = page.recipe_doc_sr().to_dict()
        total_runs = page.get_total_runs()
        render_image(page, state)
        render_description(page, state, total_runs)
        with gui.tag(
            "p",
            style={
                "color": "grey",
                "font-size": "14px",
                "float": "right",
            },
        ):
            gui.html(
                f"<svg xmlns='http://www.w3.org/2000/svg' height='16' width='16' viewBox='0 0 512 512' fill='grey'><!--!Font Awesome Free 6.5.0 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2023 Fonticons, Inc.--><path d='M156.6 384.9L125.7 354c-8.5-8.5-11.5-20.8-7.7-32.2c3-8.9 7-20.5 11.8-33.8L24 288c-8.6 0-16.6-4.6-20.9-12.1s-4.2-16.7 .2-24.1l52.5-88.5c13-21.9 36.5-35.3 61.9-35.3l82.3 0c2.4-4 4.8-7.7 7.2-11.3C289.1-4.1 411.1-8.1 483.9 5.3c11.6 2.1 20.6 11.2 22.8 22.8c13.4 72.9 9.3 194.8-111.4 276.7c-3.5 2.4-7.3 4.8-11.3 7.2v82.3c0 25.4-13.4 49-35.3 61.9l-88.5 52.5c-7.4 4.4-16.6 4.5-24.1 .2s-12.1-12.2-12.1-20.9V380.8c-14.1 4.9-26.4 8.9-35.7 11.9c-11.2 3.6-23.4 .5-31.8-7.8zM384 168a40 40 0 1 0 0-80 40 40 0 1 0 0 80z'/></svg> {total_runs} runs"
            )

    def render_image(page, state):
        gui.image(
            page.get_recipe_image(state),
            style={"border-radius": 5},
        )

    def render_description(page, state, total_runs=0):
        with gui.link(to=page.app_url()):
            gui.markdown(f"#### {page.get_recipe_title(state)}")
        preview = page.preview_description(state)
        if preview:
            gui.html(truncate_text_words(preview, 150) + "<br>")
        else:
            page.render_description()

    heading(title=TITLE, description=DESCRIPTION)
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
