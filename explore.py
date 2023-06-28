import gooey_ui as gui
from daras_ai_v2.all_pages import all_home_pages
from daras_ai_v2.face_restoration import map_parallel
from daras_ai_v2.grid_layout_widget import grid_layout


def render():
    pages = [page_cls() for page_cls in all_home_pages]

    all_examples = map_parallel(lambda page: page.get_recipe_doc().to_dict(), pages)

    def _render(args):
        page, example_doc = args

        with gui.link(to=page.app_url()):
            gui.markdown(f"## {page.title}")

        preview = page.preview_description(example_doc)
        if preview:
            gui.write(preview)
        else:
            page.render_description()

        page.render_example(example_doc)

    grid_layout(3, zip(pages, all_examples), _render)
