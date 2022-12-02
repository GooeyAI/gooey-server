from functools import wraps

import streamlit as st
from furl import furl


def patch_all():
    patch_video()
    patch_file_uploader()
    for fn in [
        st.number_input,
        st.slider,
        st.text_area,
        st.text_input,
    ]:
        patch_input_func(fn.__name__)


def patch_video():
    old_func = st.video

    @wraps(old_func)
    def new_func(url):
        f = furl(url)
        # https://muffinman.io/blog/hack-for-ios-safari-to-display-html-video-thumbnail/
        f.fragment.args["t"] = "0.001"
        return old_func(f.url)

    st.video = new_func


def patch_file_uploader():
    old_func = st.file_uploader

    @wraps(old_func)
    def new_func(label, label_visibility="markdown", **kwargs):
        if label_visibility == "markdown":
            st.write(label)
            label_visibility = "collapsed"

        value = old_func(label, label_visibility=label_visibility, **kwargs)
        st.caption(
            "By uploading, you agree to Gooey.AI's [Privacy Policy](https://dara.network/privacy)"
        )

        return value

    st.file_uploader = new_func


def patch_input_func(func_name: str):
    old_func = getattr(st, func_name)

    @wraps(old_func)
    def new_func(
        label,
        key=None,
        value=None,
        label_visibility="markdown",
        **kwargs,
    ):
        if key:
            value = st.session_state.get(key)

        if func_name.startswith("text"):
            value = value or ""

        if label_visibility == "markdown":
            st.write(label)
            label_visibility = "collapsed"

        if func_name.startswith("text"):
            # fix for https://github.com/streamlit/streamlit/issues/5604
            value = old_func(
                label,
                value=value,
                label_visibility=label_visibility,
                **kwargs,
            )
            st.session_state[key] = value
        else:
            value = old_func(
                label,
                key=key,
                label_visibility=label_visibility,
                **kwargs,
            )

        return value

    setattr(st, func_name, new_func)


patched = False
if not patched:
    patched = True
    patch_all()
