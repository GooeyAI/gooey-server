import os.path
from functools import wraps

import numpy as np
import streamlit as st
from furl import furl
from streamlit.runtime.state import get_session_state
from streamlit.runtime.uploaded_file_manager import UploadedFile


def patch(*targets):
    def decorator(patch_fn):
        for fn in targets:
            _patcher(fn.__name__, patch_fn)
        return patch_fn

    return decorator


def _patcher(fn_name, patch_fn):
    # flag to prevent multiple patch
    flag = f"__patched_{fn_name}_{patch_fn.__name__}"
    if hasattr(st, flag):
        return

    old_func = getattr(st, fn_name)

    @wraps(old_func)
    def wrapper(*args, **kwargs):
        return patch_fn(old_func, *args, **kwargs)

    setattr(st, fn_name, wrapper)
    setattr(st, flag, True)


@patch(st.image, st.audio)
def caption_patch(self, value, *args, caption=None, **kwargs):
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
    retval = self(*args, **kwargs)
    uploaded_files = st.session_state.get(upload_key)
    _render_preview(retval or uploaded_files)
    return retval


def _render_preview(file: list | UploadedFile | str | None):
    from daras_ai_v2.doc_search_settings_widgets import is_user_uploaded_url

    if isinstance(file, list):
        for item in file:
            _render_preview(item)
        return

    is_local = isinstance(file, UploadedFile)
    is_uploaded = isinstance(file, str)

    # determine appropriate filename
    if is_local:
        filename = file.name
    elif is_uploaded:
        # show only the filename for user uploaded files
        if is_user_uploaded_url(file):
            f = furl(file)
            filename = f.path.segments[-1]
        else:
            filename = file
    else:
        return

    _, col, _ = st.columns([1, 2, 1])
    with col:
        # if uploaded file, display a link to it
        if is_uploaded:
            st.write(f"🔗[*{filename}*]({file})")
        # render preview as video/image
        ext = os.path.splitext(filename)[-1].lower()
        match ext:
            case ".mp4" | ".mov" | ".ogg":
                st.video(file)
            case ".png" | ".jpg" | ".jpeg" | ".gif" | ".webp" | ".tiff":
                st.image(file)


@patch(st.text_input, st.text_area)
def text_patch(self, *args, key=None, **kwargs):
    # handle `None` value for text inputs
    if "value" in kwargs:
        kwargs["value"] = kwargs["value"] or ""
    elif key and key in st.session_state:
        st.session_state[key] = st.session_state[key] or ""

    return self(*args, key=key, **kwargs)


@patch(
    st.number_input,
    st.slider,
    st.select_slider,
    st.text_area,
    st.text_input,
    st.selectbox,
    st.multiselect,
    st.radio,
    st.file_uploader,
)
def markdown_label_patch(
    self, label=None, *args, label_visibility="markdown", **kwargs
):
    # allow full markdown labels
    if label_visibility == "markdown":
        label_visibility = "collapsed"
        if label:
            st.write(label)

    return self(label, *args, label_visibility=label_visibility, **kwargs)


INITIAL_VALUES = "__init__"


@patch(
    st.number_input,
    st.slider,
    st.select_slider,
    st.text_area,
    st.text_input,
    st.checkbox,
)
def fuck_keys(self, *args, key=None, **kwargs):
    # allow full markdown labels
    if key:
        try:
            kwargs["value"] = st.session_state[INITIAL_VALUES][key]
        except KeyError:
            if INITIAL_VALUES not in st.session_state:
                st.session_state[INITIAL_VALUES] = {}
            if key in st.session_state:
                value = st.session_state[key]
                st.session_state[INITIAL_VALUES][key] = value
                kwargs["value"] = value
        kwargs["help"] = f'{kwargs.get("help", "")} `{key}`'

    value = self(*args, **kwargs)

    if key:
        st.session_state[key] = value
    return value


@patch(
    st.selectbox,
    st.radio,
)
def fuck_keys(self, label, options, *args, key=None, **kwargs):
    # allow full markdown labels
    if key:
        try:
            value = st.session_state[INITIAL_VALUES][key]
            if value in options:
                kwargs["index"] = list(options).index(value)
        except KeyError:
            if INITIAL_VALUES not in st.session_state:
                st.session_state[INITIAL_VALUES] = {}
            if key in st.session_state:
                value = st.session_state[key]
                st.session_state[INITIAL_VALUES][key] = value
                if value in options:
                    kwargs["index"] = list(options).index(value)
        kwargs["help"] = f'{kwargs.get("help", "")} `{key}`'

    value = self(label, options, *args, **kwargs)

    if key:
        st.session_state[key] = value
    return value


# fixes https://github.com/streamlit/streamlit/issues/5620 & https://github.com/streamlit/streamlit/issues/5604
def ensure_hidden_widgets_loaded():
    if INITIAL_VALUES not in st.session_state:
        st.session_state[INITIAL_VALUES] = {}
    new_session_state = get_session_state()._state._new_session_state
    for key, value in st.session_state.items():
        if key in new_session_state or key == INITIAL_VALUES:
            continue
        st.session_state[INITIAL_VALUES][key] = value
