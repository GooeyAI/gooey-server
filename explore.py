import gooey_ui as gui
from daras_ai.image_input import truncate_text_words
from daras_ai_v2.all_pages import all_home_pages_by_category
from daras_ai_v2.grid_layout_widget import grid_layout


META_TITLE = "Explore AI workflows"
META_DESCRIPTION = "Find, fork and run your field’s favorite AI recipes on Gooey.AI"

TITLE = "Explore"
DESCRIPTION = "DISCOVER YOUR FIELD’S FAVORITE AI WORKFLOWS"


def render():
    def _render_non_featured(page_cls):
        page = page_cls()
        state = page.recipe_doc_sr().to_dict()
        # total_runs = page.get_total_runs()

        col1, col2 = gui.columns([1, 2])
        with col1:
            render_image(page, state)

        with col2:
            # render_description(page, state, total_runs)
            render_description(page, state)

    def _render_as_featured(page_cls):
        page = page_cls()
        state = page.recipe_doc_sr().to_dict()
        # total_runs = page.get_total_runs()
        render_image(page, state)
        # render_description(page, state, total_runs)
        render_description(page, state)

    def render_image(page, state):
        gui.image(
            page.get_recipe_image(state),
            style={"border-radius": 5},
        )

    def render_description(page, state):
        with gui.link(to=page.app_url()):
            gui.markdown(f"#### {page.get_recipe_title(state)}")
        preview = page.preview_description(state)
        if preview:
            with gui.tag("p", style={"margin-bottom": "2px"}):
                gui.html(
                    truncate_text_words(preview, 150),
                )
        else:
            page.render_description()
        # with gui.tag(
        #     "p",
        #     style={
        #         "font-size": "14px",
        #         "float": "right",
        #     },
        #     className="text-muted",
        # ):
        #     gui.html(
        #         f'<svg xmlns="http://www.w3.org/2000/svg" height="16" width="16" viewBox="0 0 512 512"><!--!Font Awesome Pro 6.5.0 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license (Commercial License) Copyright 2023 Fonticons, Inc.--><path d="M209.7 302.3c-15.3-15.3-34.9-25.3-55.9-28.9C187 138.8 252.2 72.6 317.8 41.7c63-29.7 128.7-27.9 171.5-19c8.8 42.8 10.7 108.5-19 171.5c-30.9 65.6-97.1 130.8-231.8 164c-3.6-21-13.6-40.6-28.9-55.9zM240 375.6l0-1.2c51.4-12.5 93.6-29.6 128-49.8l0 94.5-128 64 0-107.5zM384 424l0-109.4C522.4 223.2 520.1 79 502.7 9.3C433-8.1 288.8-10.4 197.4 128H88l-4.9 0-2.2 4.4-72 144L3.1 288H16 136.4c23.2 0 45.5 9.2 61.9 25.7s25.7 38.7 25.7 61.9V496l0 12.9 11.6-5.8 144-72 4.4-2.2 0-4.9zM137.7 272l-1.2 0H28.9l64-128h94.5c-20.2 34.4-37.3 76.6-49.8 128zm17.5 186.7c-20.7 20.7-57.3 30.6-92.1 34.7c-16.9 2-32.4 2.5-43.6 2.6c-1.2 0-2.3 0-3.4 0c0-1.1 0-2.2 0-3.4c0-11.3 .6-26.7 2.6-43.6c4.1-34.8 14.1-71.5 34.7-92.2c28.1-28.1 73.8-28.1 101.9 0s28.1 73.8 0 101.9zM166.5 470c34.4-34.4 34.4-90.1 0-124.5s-90.1-34.4-124.5 0C-7.5 395 .5 511.5 .5 511.5s116.5 8 166-41.5zM408 144a40 40 0 1 1 -80 0 40 40 0 1 1 80 0zM368 88a56 56 0 1 0 0 112 56 56 0 1 0 0-112z"/></svg> {total_runs} runs'
        #     )

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
