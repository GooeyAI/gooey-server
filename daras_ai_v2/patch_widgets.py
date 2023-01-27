import os.path
from functools import wraps

import numpy as np
import streamlit as st
from furl import furl
from streamlit.runtime.uploaded_file_manager import UploadedFile


def patch_all():
    patch_image()
    patch_video()
    patch_file_uploader()
    patch_selectbox()
    for fn in [
        st.number_input,
        st.slider,
        st.text_area,
        st.text_input,
    ]:
        patch_input_func(fn.__name__)


def patch_selectbox():
    def new_func(label, options, *args, **kwargs):
        # if selected option not in options, fallback to default choice
        if "key" in kwargs:
            key = kwargs["key"]
            if key in st.session_state:
                value = st.session_state[key]
                if value not in options:
                    st.session_state.pop(key)

        return old_func(label, options, *args, **kwargs)

    old_func = _patcher(st.selectbox.__name__, new_func)


def patch_image():
    def new_func(image, caption=None, **kwargs):
        if caption:
            st.write(f"**{caption.strip()}**")
        if isinstance(image, np.ndarray) or image:
            old_func(image)
        else:
            st.empty()

    old_func = _patcher(st.image.__name__, new_func)


def patch_video():
    def new_func(url, caption=None):
        if not url:
            st.empty()
            return

        if caption:
            st.write(f"**{caption.strip()}**")

        if isinstance(url, str):
            # https://muffinman.io/blog/hack-for-ios-safari-to-display-html-video-thumbnail/
            f = furl(url)
            f.fragment.args["t"] = "0.001"
            url = f.url

        old_func(url)

    old_func = _patcher(st.video.__name__, new_func)


def patch_file_uploader():
    def new_func(label, label_visibility="markdown", upload_key=None, **kwargs):
        if label_visibility == "markdown":
            st.write(label)
            label_visibility = "collapsed"

        value = old_func(label, label_visibility=label_visibility, **kwargs)

        # render preview from current value / uploaded value
        if value:
            preview = value
        elif upload_key in st.session_state:
            preview = st.session_state[upload_key]
        else:
            preview = None
        if preview:
            if isinstance(preview, UploadedFile):
                filename = preview.name
            else:
                filename = preview
            ext = os.path.splitext(filename)[-1].lower()
            _, mid_col, _ = st.columns([1, 2, 1])
            with mid_col:
                # render preview as video/image
                if ext in [".mp4", ".mov"]:
                    st.video(preview)
                elif ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
                    st.image(preview)

        return value

    old_func = _patcher(st.file_uploader.__name__, new_func)


def patch_input_func(func_name: str):
    def new_func(
        label,
        key=None,
        label_visibility="markdown",
        **kwargs,
    ):
        if label_visibility == "markdown":
            st.write(label)
            label_visibility = "collapsed"

        # handle `None` value for text inputs
        if func_name.startswith("text"):
            if "value" in kwargs:
                kwargs["value"] = kwargs["value"] or ""
            elif key and key in st.session_state:
                st.session_state[key] = st.session_state[key] or ""

        return old_func(
            label,
            key=key,
            label_visibility=label_visibility,
            **kwargs,
        )

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
