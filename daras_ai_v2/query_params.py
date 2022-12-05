import json

from daras_ai_v2.hidden_html_widget import hidden_html_js
import streamlit as st


def gooey_reset_query_parm(**query_params):
    st.experimental_set_query_params(**query_params, embed="true")

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
