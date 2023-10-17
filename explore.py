import gooey_ui as gui
from daras_ai.image_input import truncate_text_words
from daras_ai_v2.all_pages import all_home_pages_by_category
from daras_ai_v2.grid_layout_widget import grid_layout


def get_render_fn(title: str, description: str):
    def render():
        def _render(page_cls):
            page = page_cls()
            state = page.recipe_doc_sr().to_dict()

            with gui.link(to=page.app_url()):
                gui.markdown(f"### {page.title}")

            preview = page.preview_description(state)
            if preview:
                gui.write(truncate_text_words(preview, 150))
            else:
                page.render_description()

            page.render_example(state)

        heading(title=title, description=description)
        for category, pages in all_home_pages_by_category.items():
            separator()
            section_heading(category)
            grid_layout(3, pages, _render, separator=False)

    return render


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
        with gui.tag("span", style={"background-color": "yellow"}):
            gui.html(title.upper())


def separator(*, style: dict[str, str] | None = None):
    style = style or {}
    style_html = "".join([f"{kv[0]}: {kv[1]};" for kv in style.items()])
    gui.html(f"""<hr style="{ style_html }">""")
