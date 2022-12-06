from functools import wraps

import streamlit as st
from furl import furl


def patch_all():
    patch_image()
    patch_video()
    patch_file_uploader()
    for fn in [
        st.number_input,
        st.slider,
        st.text_area,
        st.text_input,
    ]:
        patch_input_func(fn.__name__)


def patch_image():
    def new_func(image, caption=None, **kwargs):
        if caption:
            st.write(f"**{caption.strip()}**")
        old_func(image)

    old_func = _patcher(st.image.__name__, new_func)


def patch_video():
    def new_func(url, caption=None):
        if caption:
            st.write(f"**{caption.strip()}**")

        # https://muffinman.io/blog/hack-for-ios-safari-to-display-html-video-thumbnail/
        f = furl(url)
        f.fragment.args["t"] = "0.001"
        url = f.url

        return old_func(url)

    old_func = _patcher(st.video.__name__, new_func)


def patch_file_uploader():
    def new_func(label, label_visibility="markdown", **kwargs):
        if label_visibility == "markdown":
            st.write(label)
            label_visibility = "collapsed"

        value = old_func(label, label_visibility=label_visibility, **kwargs)

        st.caption(
            "_By uploading, you agree to Gooey.AI's [Privacy Policy](https://gooey.ai/privacy)_",
        )

        return value

    old_func = _patcher(st.file_uploader.__name__, new_func)


def patch_input_func(func_name: str):
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
            # fix for https://github.comk/streamlit/streamlit/issues/5604
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

    old_func = _patcher(func_name, new_func)


def _patcher(func_name, new_func):
    # get old impl
    old_func = getattr(st, func_name)
    if hasattr(old_func, "__st_wrapped__"):
        # already wrapped, abort
        return None

    new_func = wraps(old_func)(new_func)

    # mark as wrapped
    new_func.__st_wrapped__ = True
    # replace with new impl
    setattr(st, func_name, new_func)

    # return the old impl
    return old_func


patch_all()
