import json

from daras_ai_v2.hidden_html_widget import hidden_html
import streamlit as st


def gooey_set_query_parm(**query_params):
    existing = st.experimental_get_query_params()
    existing.update(**query_params)
    st.experimental_set_query_params(**existing)

    hidden_html(
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
