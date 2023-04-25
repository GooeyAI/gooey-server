import json

import sentry_sdk
import streamlit as st

from daras_ai_v2.hidden_html_widget import hidden_html_js

_QUERY_PARAMS_KEY = "__query_params"


def gooey_get_query_params():
    try:
        return st.session_state[_QUERY_PARAMS_KEY]
    except KeyError:
        query_params = st.experimental_get_query_params()
        st.session_state[_QUERY_PARAMS_KEY] = query_params
        return query_params


def gooey_reset_query_parm(**query_params):
    # ensure the page_slug is preserved
    old_params = gooey_get_query_params()
    query_params.setdefault("page_slug", old_params.get("page_slug"))
    # update session state
    st.session_state[_QUERY_PARAMS_KEY] = query_params
    # update sentry scope
    with sentry_sdk.configure_scope() as scope:
        scope.set_extra("query_params", query_params)
    # update the url in browser
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
