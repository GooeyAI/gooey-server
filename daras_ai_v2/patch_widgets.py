import os.path
from functools import wraps

import numpy as np
import streamlit as st
from furl import furl
from streamlit.runtime.uploaded_file_manager import UploadedFile


def patch(*targets):
    def decorator(patch_fn):
        for fn in targets:
            _patcher(fn.__name__, patch_fn)
        return patch_fn

    return decorator


def _patcher(fn_name, patch_fn):
    if hasattr(st, "__patched__"):
        return

    old_func = getattr(st, fn_name)

    @wraps(old_func)
    def wrapper(*args, **kwargs):
        return patch_fn(old_func, *args, **kwargs)

    setattr(st, fn_name, wrapper)


@patch(st.image)
def image_patch(self, value, *args, caption=None, **kwargs):
    if not (isinstance(value, np.ndarray) or value):
        st.empty()
        return

    if caption:
        st.write(f"**{caption.strip()}**")

    return self(value, *args, **kwargs)


@patch(st.video)
def video_patch(self, value, *args, caption=None, **kwargs):
    if not value:
        st.empty()
        return

    if caption:
        st.write(f"**{caption.strip()}**")

    if isinstance(value, str):
        # https://muffinman.io/blog/hack-for-ios-safari-to-display-html-video-thumbnail/
        f = furl(value)
        f.fragment.args["t"] = "0.001"
        value = f.url

    return self(value, *args, **kwargs)


@patch(st.file_uploader)
def file_uploader_patch(self, *args, upload_key=None, **kwargs):
    value = self(*args, **kwargs)
    _render_preview(value, upload_key)
    return value


def _render_preview(value: UploadedFile | None, upload_key: str):
    # render preview from current value / uploaded value
    if value:
        preview = value
        filename = value.name
    elif upload_key in st.session_state:
        preview = st.session_state[upload_key]
        filename = preview
    else:
        return

    _, col, _ = st.columns([1, 2, 1])
    with col:
        # render preview as video/image
        ext = os.path.splitext(filename)[-1].lower()
        match ext:
            case ".mp4" | ".mov" | ".ogg":
                st.video(preview)
            case ".png" | ".jpg" | ".jpeg" | ".gif" | ".webp" | ".tiff":
                st.image(preview)


@patch(st.slider)
def slider_patch(self, *args, min_value=0.0, max_value=1.0, **kwargs):
    is_float = isinstance(min_value, float)
    is_int = isinstance(min_value, int)

    if is_float:
        default_step = 0.01
    elif is_int:
        default_step = 1
    else:
        return self(*args, min_value=min_value, max_value=max_value, **kwargs)

    step = kwargs.pop("step", default_step)

    options = np.arange(min_value, max_value + step, step)
    if is_float:
        options = np.round(options, 2)
    options = options.astype("object")

    return st.select_slider(*args, options=options, **kwargs)


@patch(st.selectbox)
def selectbox_patch(self, *args, key=None, options=None, **kwargs):
    # if selected option not in options, fallback to default choice
    if key and key in st.session_state:
        value = st.session_state[key]
        if options and value not in options:
            st.session_state.pop(key)

    return self(*args, key=key, options=options, **kwargs)


@patch(st.text_input, st.text_area)
def text_patch(self, *args, key=None, **kwargs):
    # handle `None` value for text inputs
    if "value" in kwargs:
        kwargs["value"] = kwargs["value"] or ""
    elif key and key in st.session_state:
        st.session_state[key] = st.session_state[key] or ""

    return self(*args, key=key, **kwargs)


common_inputs = [
    st.number_input,
    st.slider,
    st.select_slider,
    st.text_area,
    st.text_input,
    st.selectbox,
    st.multiselect,
    st.radio,
]


@patch(*common_inputs, st.file_uploader)
def markdown_label_patch(self, label, *args, label_visibility="markdown", **kwargs):
    # allow full markdown labels
    if label_visibility == "markdown":
        st.write(label)
        label_visibility = "collapsed"

    return self(label, *args, label_visibility=label_visibility, **kwargs)


# fixes https://github.com/streamlit/streamlit/issues/5620 & https://github.com/streamlit/streamlit/issues/5604
@patch(*common_inputs, st.checkbox)
def shadow_keys_patch(self, *args, key=None, **kwargs):
    if key:
        underlying_key = "__shadow_" + key
        if key in st.session_state and underlying_key not in st.session_state:
            st.session_state[underlying_key] = st.session_state[key]
    else:
        underlying_key = key

    ret = self(*args, key=underlying_key, **kwargs)

    if key and underlying_key in st.session_state:
        st.session_state[key] = st.session_state[underlying_key]

    return ret


st.__patched__ = True
