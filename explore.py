import streamlit as st
from furl import furl
from google.cloud.firestore_v1 import DocumentSnapshot

from daras_ai.db import list_all_docs
from daras_ai_v2 import settings
from daras_ai_v2.all_pages import all_home_pages
from daras_ai_v2.face_restoration import map_parallel
from daras_ai_v2.grid_layout_widget import grid_layout


def render():
    pages = [page_cls() for page_cls in all_home_pages]

    with st.spinner():
        all_examples = map_parallel(lambda page: page.get_recipe_doc().to_dict(), pages)

    grid_layout(3, zip(pages, all_examples), _render)

    with st.expander("Early Recipes"):
        for snapshot in list_all_docs():
            snapshot: DocumentSnapshot

            recipe_id = snapshot.id
            doc = snapshot.to_dict()

            if doc.get("header_is_hidden"):
                continue
            name = doc.get("header_title", doc.get(""))
            if not name:
                continue

            tagline = doc.get("header_tagline", "")
            editor_url = (
                furl(settings.APP_BASE_URL, query_params={"id": recipe_id}) / "Editor/"
            )

            st.markdown(
                f"""
                <a style="font-size: 24px" href="{editor_url}" target = "_top">
                    {name}
                </a>
                <br>
                <i>{tagline}</i>
                """,
                unsafe_allow_html=True,
            )


def _render(args):
    page, example_doc = args

    st.markdown(
        f"""
        <a style="font-size: 24px" href="{page.app_url()}" target = "_top">
            <h2>{page.title}</h2>
        </a>
        """,
        unsafe_allow_html=True,
    )

    preview = page.preview_description(example_doc)
    if preview:
        st.write(preview)
    else:
        page.render_description()

    page.render_example(example_doc)
