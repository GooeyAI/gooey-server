import json

import sentry_sdk
import streamlit as st

from daras_ai_v2.hidden_html_widget import hidden_html_js


def gooey_reset_query_parm(**query_params):
    st_params = st.experimental_get_query_params()
    st_params = dict(
        **query_params,
        page_slug=st_params.get("page_slug"),
        embed=st_params.get("embed"),
    )
    st.experimental_set_query_params(**st_params)

    hidden_html_js(
        """
        <script>
            top.postMessage({
                "type": "GOOEY_SET_QUERY_PARAM",
                "queryParams": %s,
            }, "*");
        </script>
        """
        % json.dumps(query_params)
    )

    with sentry_sdk.configure_scope() as scope:
        scope.set_extra("query_params", st_params)
