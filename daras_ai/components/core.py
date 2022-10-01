from functools import wraps

import streamlit as st

REPO = {}


def daras_ai_step(verbose_name=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(idx, delete, **kwargs):
            if verbose_name:
                with st.expander(verbose_name):
                    if st.button("🗑", help=f"Delete Step {idx + 1}"):
                        delete()
                        return
                    fn(**kwargs)
            else:
                fn(**kwargs)

        REPO[wrapper.__name__] = wrapper
        wrapper.verbose_name = verbose_name
        return wrapper

    return decorator
