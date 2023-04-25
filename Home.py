from daras_ai.init import init_scripts

init_scripts()

import streamlit as st

from daras_ai_v2.query_params import gooey_get_query_params
from server import normalize_slug, page_map

# try to load page from query params
#
query_params = gooey_get_query_params()
try:
    page_slug = normalize_slug(query_params["page_slug"][0])
except KeyError:
    # no page_slug provided - render explore page
    import explore

    explore.render()
else:
    try:
        page = page_map[page_slug]
    except KeyError:
        st.error(f"## 404 - Page {page_slug!r} Not found")
    else:
        page().render()
