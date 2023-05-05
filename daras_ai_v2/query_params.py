import sentry_sdk

import gooey_ui as st


def gooey_get_query_params():
    return st.get_query_params()


def gooey_reset_query_parm(**query_params):
    fixed_params = gooey_get_query_params()
    fixed_params = query_params | dict(
        page_slug=fixed_params.get("page_slug"),
        tab=fixed_params.get("tab"),
    )
    # update the params in browser
    st.set_query_params(fixed_params)
    # update sentry scope
    with sentry_sdk.configure_scope() as scope:
        scope.set_extra("query_params", fixed_params)
