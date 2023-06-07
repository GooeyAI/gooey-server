import base64
import os
import textwrap
import typing

import numpy as np
import pandas as pd
from furl import furl

from gooey_ui import state
from gooey_ui.pubsub import md5_values
from gooey_ui.state import Style, Props

T = typing.TypeVar("T")
LabelVisibility = typing.Literal["visible", "collapsed"]


def dummy(*args, **kwargs):
    return state.NestingCtx()


spinner = dummy
set_page_config = dummy
form = dummy
plotly_chart = dummy
dataframe = dummy


def nav_tabs():
    return tag("nav-tabs")


def nav_item(href: str, *, active: bool):
    return tag("nav-item", props=dict(href=href, active=active))


def nav_tab_content():
    return tag("nav-tab-content")


def div(*, style: Style = None, **attrs) -> typing.ContextManager:
    return tag("div", style=style, props=attrs)


def tag(
    name: str, *, style: Style = None, props: Props = None
) -> typing.ContextManager:
    node = state.RenderTreeNode(name=name, props=props or {}, style=style or {})
    node.mount()
    return state.NestingCtx(node)


def html(body: str, height: int = None, width: int = None):
    state.RenderTreeNode(
        name="html",
        style=dict(height=f"{height}px", width=f"{width}px"),
        props=dict(body=body),
    ).mount()


def write(*objs: typing.Any, unsafe_allow_html=False):
    for obj in objs:
        markdown(
            obj if isinstance(obj, str) else repr(obj),
            unsafe_allow_html=unsafe_allow_html,
        )


def markdown(body: str, *, style: dict[str, str] = None, unsafe_allow_html=False):
    state.RenderTreeNode(
        name="markdown",
        style=style or {},
        props=dict(body=dedent(body), unsafe_allow_html=unsafe_allow_html),
    ).mount()


def text(body: str, *, style: dict[str, str] = None, unsafe_allow_html=False):
    state.RenderTreeNode(
        name="pre",
        style=style or {},
        props=dict(body=dedent(body), unsafe_allow_html=unsafe_allow_html),
    ).mount()


def error(body: str, icon: str = "⚠️", *, unsafe_allow_html=False):
    if not isinstance(body, str):
        body = repr(body)
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


def success(body: str, icon: str = "✅", *, unsafe_allow_html=False):
    markdown(
        # language="html",
        f"""
<div style="background-color: rgba(108, 255, 108, 0.2); padding: 16px; border-radius: 0.25rem; display: flex; gap: 0.5rem;">
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
    parent = state.RenderTreeNode(
        name="tabs",
        children=[
            state.RenderTreeNode(
                name="tab",
                props=dict(label=dedent(label)),
            )
            for label in labels
        ],
    ).mount()
    return [state.NestingCtx(tab) for tab in parent.children]


def columns(spec, *, gap: str = None) -> list[typing.ContextManager]:
    if isinstance(spec, int):
        spec = [1] * spec
    total_weight = sum(spec)
    parent = state.RenderTreeNode(
        name="div",
        style=dict(
            display="flex",
            gap="1 rem",
        ),
        children=[
            state.RenderTreeNode(
                name="div",
                style={"width": p, "flexBasis": p},
            )
            for w in spec
            if (p := f"{w / total_weight * 100:.2f}%")
        ],
    )
    parent.mount()
    return [state.NestingCtx(tab) for tab in parent.children]


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
    state.RenderTreeNode(
        name="img",
        style=dict(width=f"{width}px"),
        props=dict(src=src, caption=caption, alt=alt),
    ).mount()


def video(src: str, caption: str = None):
    if not src:
        return
    if isinstance(src, str):
        # https://muffinman.io/blog/hack-for-ios-safari-to-display-html-video-thumbnail/
        f = furl(src)
        f.fragment.args["t"] = "0.001"
        src = f.url
    state.RenderTreeNode(
        name="video",
        props=dict(src=src, caption=caption),
    ).mount()


def audio(src: str, caption: str = None):
    if not src:
        return
    state.RenderTreeNode(
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
        value = state.session_state.get(key)
    if label_visibility != "visible":
        label = None
    state.RenderTreeNode(
        name="textarea",
        style=dict(height=f"{height}px"),
        props=dict(
            name=key,
            label=dedent(label),
            defaultValue=value,
            help=help,
            placeholder=placeholder,
            disabled=disabled,
        ),
    ).mount()
    return value or ""


def multiselect(
    label: str,
    options: typing.Sequence[T],
    format_func: typing.Callable[[T], typing.Any] = str,
    key: str = None,
    help: str = None,
    *,
    disabled: bool = False,
) -> list[T]:
    if not options:
        return []
    options = list(options)
    if not key:
        key = md5_values("multiselect", label, options, help)
    value = state.session_state.get(key) or []
    value = [o if o in options else options[0] for o in value]
    state.session_state.setdefault(key, value)
    state.RenderTreeNode(
        name="select",
        props=dict(
            name=key,
            label=dedent(label),
            help=help,
            isDisabled=disabled,
            isMulti=True,
            defaultValue=[
                {"value": option, "label": str(format_func(option))} for option in value
            ],
            options=[
                {"value": option, "label": str(format_func(option))}
                for option in options
            ],
        ),
    ).mount()
    return value


def selectbox(
    label: str,
    options: typing.Sequence[T],
    format_func: typing.Callable[[T], typing.Any] = str,
    key: str = None,
    help: str = None,
    *,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
) -> T | None:
    if not options:
        return None
    if label_visibility != "visible":
        label = None
    options = list(options)
    if not key:
        key = md5_values("select", label, options, help, label_visibility)
    value = state.session_state.get(key)
    if value not in options:
        value = options[0]
    state.session_state.setdefault(key, value)
    state.RenderTreeNode(
        name="select",
        props=dict(
            name=key,
            label=dedent(label),
            help=help,
            isDisabled=disabled,
            defaultValue={"value": value, "label": str(format_func(value))},
            options=[
                {"value": option, "label": str(format_func(option))}
                for option in options
            ],
        ),
    ).mount()
    return value


def button(
    label: str,
    key: str = None,
    help: str = None,
    *,
    type: typing.Literal["primary", "secondary"] = "secondary",
    disabled: bool = False,
) -> bool:
    if not key:
        key = md5_values("button", label, help, type, disabled)
    state.RenderTreeNode(
        name="button",
        props=dict(
            type="submit",
            value="yes",
            name=key,
            label=dedent(label),
            help=help,
            disabled=disabled,
        ),
    ).mount()
    return bool(state.session_state.pop(key, False))


form_submit_button = button


def expander(label: str, *, expanded: bool = False):
    node = state.RenderTreeNode(
        name="details",
        props=dict(
            label=dedent(label),
            open=expanded,
        ),
    )
    node.mount()
    return state.NestingCtx(node)


def file_uploader(
    label: str,
    accept: list[str] = None,
    accept_multiple_files=False,
    key: str = None,
    upload_key: str = None,
    help: str = None,
    *,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
):
    if label_visibility != "visible":
        label = None
    key = upload_key or key
    value = state.session_state.get(key)
    if not value:
        if accept_multiple_files:
            value = []
        else:
            value = ""
    state.session_state[key] = value
    state.RenderTreeNode(
        name="input",
        props=dict(
            type="file",
            name=key,
            label=dedent(label),
            help=help,
            disabled=disabled,
            accept=accept,
            multiple=accept_multiple_files,
            defaultValue=value,
        ),
    ).mount()
    return value or ""


def json(value: typing.Any, expanded: bool = False):
    state.RenderTreeNode(
        name="json",
        props=dict(
            value=value,
            expanded=expanded,
            defaultInspectDepth=3 if expanded else 1,
        ),
    ).mount()


def table(df: pd.DataFrame):
    state.RenderTreeNode(
        name="table",
        children=[
            state.RenderTreeNode(
                name="thead",
                children=[
                    state.RenderTreeNode(
                        name="tr",
                        children=[
                            state.RenderTreeNode(
                                name="th",
                                children=[
                                    state.RenderTreeNode(
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
            state.RenderTreeNode(
                name="tbody",
                children=[
                    state.RenderTreeNode(
                        name="tr",
                        children=[
                            state.RenderTreeNode(
                                name="td",
                                children=[
                                    state.RenderTreeNode(
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


def radio(
    label: str,
    options: typing.Sequence[T],
    format_func: typing.Callable[[T], typing.Any] = str,
    key: str = None,
    help: str = None,
    *,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
) -> T | None:
    if not options:
        return None
    options = list(options)
    if not key:
        key = md5_values("radio", label, options, help, label_visibility)
    value = state.session_state.get(key)
    if value not in options:
        value = options[0]
    state.session_state.setdefault(key, value)
    if label_visibility != "visible":
        label = None
    markdown(label)
    for option in options:
        state.RenderTreeNode(
            name="input",
            props=dict(
                type="radio",
                name=key,
                label=dedent(str(format_func(option))),
                value=option,
                defaultChecked=bool(value == option),
                help=help,
                disabled=disabled,
            ),
        ).mount()
    return value


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
    value = _input_widget(
        input_type="text",
        label=label,
        value=value,
        key=key,
        help=help,
        disabled=disabled,
        label_visibility=label_visibility,
        maxLength=max_chars,
        placeholder=placeholder,
    )
    return value or ""


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
    value = _input_widget(
        input_type="range",
        label=label,
        value=value,
        key=key,
        help=help,
        disabled=disabled,
        min=min_value,
        max=max_value,
        step=_step_value(min_value, max_value, step),
    )
    return value or 0


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
    value = _input_widget(
        input_type="number",
        inputMode="decimal",
        label=label,
        value=value,
        key=key,
        help=help,
        disabled=disabled,
        min=min_value,
        max=max_value,
        step=_step_value(min_value, max_value, step),
    )
    return value or 0


def _step_value(
    min_value: float | None, max_value: float | None, step: float | None
) -> float:
    if step:
        return step
    elif isinstance(min_value, float) or isinstance(max_value, float):
        return 0.1
    else:
        return 1


def checkbox(
    label: str,
    value: bool = False,
    key: str = None,
    help: str = None,
    *,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
) -> bool:
    value = _input_widget(
        input_type="checkbox",
        label=label,
        value=value,
        key=key,
        help=help,
        disabled=disabled,
        label_visibility=label_visibility,
        default_value_attr="defaultChecked",
    )
    return bool(value)


def _input_widget(
    *,
    input_type: str,
    label: str,
    value: typing.Any = None,
    key: str = None,
    help: str = None,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
    default_value_attr: str = "defaultValue",
    **kwargs,
) -> typing.Any:
    if key:
        assert not value, "only one of value or key can be provided"
    else:
        key = md5_values("input", input_type, label, help, label_visibility)
    value = state.session_state.setdefault(key, value)
    if label_visibility != "visible":
        label = None
    state.RenderTreeNode(
        name="input",
        props={
            "type": input_type,
            "name": key,
            "label": dedent(label),
            default_value_attr: value,
            "help": help,
            "disabled": disabled,
            **kwargs,
        },
    ).mount()
    return value


def dedent(text: str | None) -> str | None:
    if not text:
        return text
    return textwrap.dedent(text)
