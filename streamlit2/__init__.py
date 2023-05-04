import base64
import os
import typing
from contextlib import contextmanager
from functools import lru_cache
import textwrap

import numpy as np
import pandas as pd
from furl import furl
from pydantic import BaseModel
from streamlit.type_util import LabelVisibility, OptionSequence


Style = dict[str, str | None]
T = typing.TypeVar("T")

query_params: dict = None
session_state: dict = None
render_root: "RenderTreeNode" = None


def dedent(text: str | None) -> str | None:
    if not text:
        return text
    return textwrap.dedent(text)


class RenderTreeNode(BaseModel):
    name: str
    props: dict[str, typing.Any] = {}
    children: list["RenderTreeNode"] = []
    style: Style = {}

    def mount(self) -> "RenderTreeNode":
        render_root.children.append(self)
        return self


def get_query_params():
    return query_params


class UploadedFile:
    pass


def dummy(*args, **kwargs):
    return _node_ctx(render_root)


spinner = dummy
set_page_config = dummy
experimental_rerun = dummy
form = dummy


@contextmanager
def _node_ctx(node: RenderTreeNode):
    global render_root
    old = render_root
    render_root = node
    try:
        yield
    finally:
        render_root = old


def div() -> typing.ContextManager:
    node = RenderTreeNode(name="div")
    node.mount()
    return _node_ctx(node)


def cache_data(fn=None, *args, **kwargs):
    if not fn:
        return lru_cache
    return lru_cache(fn)


def cache_resource(fn=None, *args, **kwargs):
    if not fn:
        return lru_cache
    return lru_cache(fn)


def html(body: str, height: int = None, width: int = None):
    RenderTreeNode(
        name="html",
        style=dict(height=f"{height}px", width=width),
        props=dict(body=body),
    ).mount()


def write(*objs: typing.Any, unsafe_allow_html=False):
    for obj in objs:
        markdown(
            obj if isinstance(obj, str) else repr(obj),
            unsafe_allow_html=unsafe_allow_html,
        )


def markdown(body: str, *, style: dict[str, str] = None, unsafe_allow_html=False):
    RenderTreeNode(
        name="markdown",
        style=style or {},
        props=dict(body=dedent(body), unsafe_allow_html=unsafe_allow_html),
    ).mount()


def text(body: str, *, style: dict[str, str] = None, unsafe_allow_html=False):
    RenderTreeNode(
        name="pre",
        style=style or {},
        props=dict(body=dedent(body), unsafe_allow_html=unsafe_allow_html),
    ).mount()


def error(body: str, icon: str = None, *, unsafe_allow_html=False):
    markdown(
        # language="html",
        f"""
<div style="background-color: rgba(255, 108, 108, 0.2); padding: 16px; border-radius: 0.25rem; display: flex; gap: 0.5rem;">
<span style="font-size: 1.25rem">{icon}</span>
<div>{dedent(body)}</div>
</div>
            """,
        unsafe_allow_html=True,
    )


def success(body: str, icon: str = None, *, unsafe_allow_html=False):
    markdown(
        # language="html",
        f"""
<div style="background-color: green; padding: 16px; border-radius: 0.25rem; display: flex; gap: 0.5rem;">
<span style="font-size: 1.25rem">{icon}</span>
<div>{dedent(body)}</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def caption(body: str):
    markdown(body, style={"fontSize": "0.75rem"})


def option_menu(*args, options, **kwargs):
    return tabs(options)


def tabs(labels: list[str]) -> list[typing.ContextManager]:
    parent = RenderTreeNode(
        name="tabs",
        children=[
            RenderTreeNode(
                name="tab",
                props=dict(label=dedent(label)),
            )
            for label in labels
        ],
    ).mount()
    return [_node_ctx(tab) for tab in parent.children]


def columns(spec, *, gap: str = None) -> list[typing.ContextManager]:
    if isinstance(spec, int):
        spec = [1] * spec
    total_weight = sum(spec)
    parent = RenderTreeNode(
        name="columns",
        children=[
            RenderTreeNode(
                name="div",
                style={"width": p, "flexBasis": p},
            )
            for w in spec
            if (p := f"{w / total_weight * 100:.2f}%")
        ],
    )
    parent.mount()
    return [_node_ctx(tab) for tab in parent.children]


def image(
    src: str | np.ndarray, caption: str = None, alt: str = None, width: int = None
):
    if isinstance(src, np.ndarray):
        from daras_ai.image_input import cv2_img_to_bytes

        # convert to base64 and set src
        data = cv2_img_to_bytes(src)
        b64 = base64.b64encode(data).decode("utf-8")
        src = "data:image/png;base64," + b64
    if not src:
        return
    RenderTreeNode(
        name="img",
        style=dict(width=width),
        props=dict(src=src, caption=caption, alt=alt),
    ).mount()


def video(src: str, caption: str = None):
    if not (isinstance(src, np.ndarray) or src):
        return
    src += "#t=0.001"
    RenderTreeNode(
        name="video",
        props=dict(src=src, caption=caption),
    ).mount()


def audio(src: str, caption: str = None):
    if not (isinstance(src, np.ndarray) or src):
        return
    RenderTreeNode(
        name="audio",
        props=dict(src=src, caption=caption),
    ).mount()


def text_area(
    label: str,
    value: str = "",
    height: int = 100,
    key: str = None,
    help: str = None,
    placeholder: str = None,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
) -> str:
    if key:
        assert not value, "only one of value or key can be provided"
        value = session_state.get(key)
    if label_visibility != "visible":
        label = None
    RenderTreeNode(
        name="textarea",
        style=dict(height=f"{height}px"),
        props=dict(
            label=dedent(label),
            value=value,
            help=help,
            placeholder=placeholder,
            disabled=disabled,
        ),
    ).mount()
    return value or ""


def checkbox(
    label: str,
    value: bool = False,
    key: str = None,
    help: str = None,
    *,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
) -> bool:
    if key:
        assert not value, "only one of value or key can be provided"
        value = session_state.get(key)
    if label_visibility != "visible":
        label = None
    RenderTreeNode(
        name="input",
        props=dict(
            type="checkbox",
            name=key,
            label=dedent(label),
            defaultValue=value,
            help=help,
            disabled=disabled,
        ),
    ).mount()
    return bool(value)


def radio(
    label: str,
    options: OptionSequence[T],
    index: int = 0,
    format_func: typing.Callable[[T], typing.Any] = str,
    key: str = None,
    help: str = None,
    *,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
) -> typing.Optional[T]:
    if not options:
        return None
    options = list(options)
    if key:
        value = session_state.get(key)
    else:
        value = None
    value = value or options[index]
    if label_visibility != "visible":
        label = None
    markdown(label)
    for option in options:
        RenderTreeNode(
            name="input",
            props=dict(
                type="radio",
                name=key,
                label=dedent(str(format_func(option))),
                defaultValue=value,
                help=help,
                disabled=disabled,
            ),
        ).mount()
    return bool(value)


def selectbox(
    label: str,
    options: OptionSequence[T],
    index: int = 0,
    format_func: typing.Callable[[T], typing.Any] = str,
    key: str = None,
    help: str = None,
    *,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
):
    if not options:
        return None
    options = list(options)
    if key:
        value = session_state.get(key) or options[index]
    else:
        value = None
    value = value or options[index]
    if label_visibility != "visible":
        label = None
    RenderTreeNode(
        name="select",
        props=dict(
            label=dedent(label),
            help=help,
            disabled=disabled,
        ),
        children=[
            RenderTreeNode(
                name="option",
                props=dict(
                    label=dedent(str(format_func(option))),
                    value=option,
                    selected=value == options[index],
                ),
            )
            for option in options
        ],
    )
    return value


def button(
    label: str,
    key: str = None,
    help: str = None,
    *,
    type: typing.Literal["primary", "secondary"] = "secondary",
    disabled: bool = False,
) -> bool:
    RenderTreeNode(
        name="button",
        props=dict(
            label=dedent(label),
            type=type,
            help=help,
            disabled=disabled,
        ),
    ).mount()
    return False


form_submit_button = button


def expander(label: str, *, expanded: bool = False):
    node = RenderTreeNode(
        name="details",
        props=dict(
            label=dedent(label),
            open=expanded,
        ),
    )
    node.mount()
    return _node_ctx(node)


def number_input(
    label: str,
    min_value: float = None,
    max_value: float = None,
    value: float = None,
    step: float = None,
    key: str = None,
    help: str = None,
    *,
    disabled: bool = False,
) -> float:
    if key:
        assert not value, "only one of value or key can be provided"
        value = session_state.get(key)
    RenderTreeNode(
        name="input",
        props=dict(
            type="number",
            name=key,
            label=dedent(label),
            defaultValue=value,
            help=help,
            disabled=disabled,
            min=min_value,
            max=max_value,
            step=step or (0.1 if isinstance(min_value, float) else 1),
        ),
    ).mount()
    return value or 0


def slider(
    label: str,
    min_value: float = None,
    max_value: float = None,
    value: float = None,
    step: float = None,
    key: str = None,
    help: str = None,
    *,
    disabled: bool = False,
) -> float:
    if key:
        assert not value, "only one of value or key can be provided"
        value = session_state.get(key)
    RenderTreeNode(
        name="input",
        props=dict(
            type="range",
            name=key,
            label=dedent(label),
            defaultValue=value,
            help=help,
            disabled=disabled,
            min=min_value,
            max=max_value,
            step=step or (0.1 if isinstance(min_value, float) else 1),
        ),
    ).mount()
    return value or 0


def text_input(
    label: str,
    value: str = "",
    max_chars: str = None,
    key: str = None,
    help: str = None,
    *,
    placeholder: str = None,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
) -> str:
    if key:
        assert not value, "only one of value or key can be provided"
        value = session_state.get(key)
    if label_visibility != "visible":
        label = None
    RenderTreeNode(
        name="input",
        props=dict(
            type="text",
            name=key,
            label=dedent(label),
            defaultValue=value,
            help=help,
            disabled=disabled,
            maxLength=max_chars,
            placeholder=placeholder,
        ),
    ).mount()
    return value or ""


def file_uploader(
    label: str,
    type: str | list[str] = None,
    accept_multiple_files=False,
    key: str = None,
    upload_key: str = None,
    help: str = None,
    *,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
):
    value = session_state.get(key)
    if label_visibility != "visible":
        label = None
    if type:
        if isinstance(type, str):
            type = [type]
        accept = ",".join(type)
    else:
        accept = None
    RenderTreeNode(
        name="input",
        props=dict(
            type="file",
            name=upload_key or key,
            label=dedent(label),
            help=help,
            disabled=disabled,
            accept=accept,
            multiple=accept_multiple_files,
        ),
    ).mount()
    _render_preview(value)
    return value or ""


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

    _, col, _ = columns([1, 2, 1])
    with col:
        # if uploaded file, display a link to it
        if is_uploaded:
            markdown(f"🔗[*{filename}*]({file})")
        # render preview as video/image
        ext = os.path.splitext(filename)[-1].lower()
        match ext:
            case ".mp4" | ".mov" | ".ogg":
                video(file)
            case ".png" | ".jpg" | ".jpeg" | ".gif" | ".webp" | ".tiff":
                image(file)


def json(value: typing.Any, expanded: bool = False):
    RenderTreeNode(
        name="json",
        props=dict(
            value=value,
            expanded=expanded,
            collapseStringsAfterLength=False if expanded else 0,
        ),
    ).mount()


def table(df: pd.DataFrame):
    RenderTreeNode(
        name="table",
        children=[
            RenderTreeNode(
                name="thead",
                children=[
                    RenderTreeNode(
                        name="tr",
                        children=[
                            RenderTreeNode(
                                name="th",
                                children=[
                                    RenderTreeNode(
                                        name="markdown",
                                        props=dict(body=dedent(col)),
                                    ),
                                ],
                            )
                            for col in df.columns
                        ],
                    ),
                ],
            ),
            RenderTreeNode(
                name="tbody",
                children=[
                    RenderTreeNode(
                        name="tr",
                        children=[
                            RenderTreeNode(
                                name="td",
                                children=[
                                    RenderTreeNode(
                                        name="markdown",
                                        props=dict(body=dedent(str(value))),
                                    ),
                                ],
                            )
                            for value in row
                        ],
                    )
                    for row in df.itertuples(index=False)
                ],
            ),
        ],
    ).mount()


def stop():
    exit(0)
