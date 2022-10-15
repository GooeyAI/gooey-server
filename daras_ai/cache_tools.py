from functools import wraps
from threading import Thread

import streamlit as st


def cache_and_refresh(fn):
    @st.cache(allow_output_mutation=True)
    def cached_fn(*args, **kwargs):
        return {"value": fn(*args, **kwargs)}

    @wraps(fn)
    def wrapper(*args, **kwargs):
        ret = cached_fn(*args, **kwargs)

        def refresh_cache():
            ret["value"] = fn(*args, **kwargs)

        Thread(target=refresh_cache).start()

        return ret["value"]

    return wrapper
