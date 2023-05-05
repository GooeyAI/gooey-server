import json

import sentry_sdk
import streamlit as st

from daras_ai_v2.hidden_html_widget import hidden_html_js

QUERY_PARAMS_KEY = "__query_params"


def gooey_get_query_params():
    try:
        return st.session_state[QUERY_PARAMS_KEY]
    except KeyError:
        query_params = st.experimental_get_query_params()
        st.session_state[QUERY_PARAMS_KEY] = query_params
        return query_params


def gooey_reset_query_parm(**public_params):
    old_params = gooey_get_query_params()
    # ensure the page_slug is preserved
    new_params = dict(
        **public_params,
        page_slug=old_params.get("page_slug"),
    )
    # update session state
    st.session_state[QUERY_PARAMS_KEY] = new_params
    # update sentry scope
    with sentry_sdk.configure_scope() as scope:
        scope.set_extra("query_params", new_params)
    # update the url in browser, only show the public params
    hidden_html_js(
        # language=HTML
        """
<script>
    top.postMessage({
        "type": "GOOEY_SET_QUERY_PARAM",
        "queryParams": %s,
    }, "*");
</script>
        """
        % json.dumps(public_params)
    )
