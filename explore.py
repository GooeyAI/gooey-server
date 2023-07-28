import gooey_ui as gui
from daras_ai.image_input import truncate_text_words
from daras_ai_v2.all_pages import all_home_pages
from daras_ai_v2.grid_layout_widget import grid_layout


def render():
    def _render(page_cls):
        page = page_cls()
        state = page.recipe_doc_sr().to_dict()

        with gui.link(to=page.app_url()):
            gui.markdown(f"## {page.title}")

        preview = page.preview_description(state)
        if preview:
            gui.write(truncate_text_words(preview, 150))
        else:
            page.render_description()

        page.render_example(state)

    grid_layout(3, all_home_pages, _render)
