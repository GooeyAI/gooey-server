import sentry_sdk

import gooey_ui as st

QUERY_PARAMS_KEY = "__query_params__"


def gooey_get_query_params():
    return st.get_query_params()


def gooey_reset_query_parm(**query_params):
    # update the params in browser
    st.set_query_params(query_params)
    # update sentry scope
    with sentry_sdk.configure_scope() as scope:
        scope.set_extra("query_params", query_params)
