import gooey_ui as st

QUERY_PARAMS_KEY = "__query_params__"


def gooey_get_query_params():
    return st.get_query_params()
