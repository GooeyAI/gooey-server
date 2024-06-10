import base64
import html as html_lib
import math
import textwrap
import typing
from datetime import datetime, timezone

import numpy as np
from furl import furl

from daras_ai.image_input import resize_img_scale
from daras_ai_v2.enum_selector_widget import BLANK_OPTION
from gooey_ui import state
from gooey_ui.pubsub import md5_values

T = typing.TypeVar("T")
LabelVisibility = typing.Literal["visible", "collapsed"]


def _default_format(value: typing.Any) -> str:
    if value is None:
        return BLANK_OPTION
    return str(value)


def dummy(*args, **kwargs):
    return state.NestingCtx()


spinner = dummy
set_page_config = dummy
form = dummy
dataframe = dummy


def countdown_timer(
    end_time: datetime,
    delay_text: str,
) -> state.NestingCtx:
    return _node(
        "countdown-timer",
        endTime=end_time.astimezone(timezone.utc).isoformat(),
        delayText=delay_text,
    )


def nav_tabs():
    return _node("nav-tabs")


def nav_item(href: str, *, active: bool):
    return _node("nav-item", to=href, active="true" if active else None)


def nav_tab_content():
    return _node("nav-tab-content")


def div(**props) -> state.NestingCtx:
    return tag("div", **props)


def link(*, to: str, **props) -> state.NestingCtx:
    return _node("Link", to=to, **props)


def tag(tag_name: str, **props) -> state.NestingCtx:
    props["__reactjsxelement"] = tag_name
    return _node("tag", **props)


def html(body: str, **props):
    props["className"] = props.get("className", "") + " gui-html-container"
    return _node("html", body=body, **props)


def write(*objs: typing.Any, line_clamp: int = None, unsafe_allow_html=False, **props):
    for obj in objs:
        markdown(
            obj if isinstance(obj, str) else repr(obj),
            line_clamp=line_clamp,
            unsafe_allow_html=unsafe_allow_html,
            **props,
        )


def center(direction="flex-column", className="") -> state.NestingCtx:
    return div(
        className=f"d-flex justify-content-center align-items-center text-center {direction} {className}"
    )


def newline():
    html("<br/>")


def markdown(
    body: str | None, *, line_clamp: int = None, unsafe_allow_html=False, **props
):
    if body is None:
        return _node("markdown", body="", **props)
    if not unsafe_allow_html:
        body = html_lib.escape(body)
    props["className"] = (
        props.get("className", "") + " gui-html-container gui-md-container"
    )
    return _node("markdown", body=dedent(body).strip(), lineClamp=line_clamp, **props)


def _node(name: str, **props):
    node = state.RenderTreeNode(name=name, props=props)
    node.mount()
    return state.NestingCtx(node)


def text(body: str, **props):
    state.RenderTreeNode(
        name="pre",
        props=dict(body=dedent(body), **props),
    ).mount()


def error(
    body: str,
    icon: str = "🔥",
    *,
    unsafe_allow_html=False,
    color="rgba(255, 108, 108, 0.2)",
):
    if not isinstance(body, str):
        body = repr(body)
    with div(
        style=dict(
            backgroundColor=color,
            padding="1rem",
            paddingBottom="0",
            marginBottom="0.5rem",
            borderRadius="0.25rem",
            display="flex",
            gap="0.5rem",
        )
    ):
        markdown(icon)
        with div():
            markdown(dedent(body), unsafe_allow_html=unsafe_allow_html)


def success(body: str, icon: str = "✅", *, unsafe_allow_html=False):
    if not isinstance(body, str):
        body = repr(body)
    with div(
        style=dict(
            backgroundColor="rgba(108, 255, 108, 0.2)",
            padding="1rem",
            paddingBottom="0",
            marginBottom="0.5rem",
            borderRadius="0.25rem",
            display="flex",
            gap="0.5rem",
        )
    ):
        markdown(icon)
        markdown(dedent(body), unsafe_allow_html=unsafe_allow_html)


def caption(body: str, className: str = None, **props):
    className = className or "text-muted"
    markdown(body, className=className, **props)


def tabs(labels: list[str]) -> list[state.NestingCtx]:
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


def controllable_tabs(
    labels: list[str], key: str
) -> tuple[list[state.NestingCtx], int]:
    index = state.session_state.get(key, 0)
    for i, label in enumerate(labels):
        if button(
            label,
            key=f"tab-{i}",
            type="primary",
            className="replicate-nav",
            style={
                "background": "black" if i == index else "white",
                "color": "white" if i == index else "black",
            },
        ):
            state.session_state[key] = index = i
            state.experimental_rerun()
    ctxs = []
    for i, label in enumerate(labels):
        if i == index:
            ctxs += [div(className="tab-content")]
        else:
            ctxs += [div(className="tab-content", style={"display": "none"})]
    return ctxs, index


def columns(
    spec,
    *,
    gap: str = None,
    responsive: bool = True,
    column_props: dict = {},
    **props,
) -> tuple[state.NestingCtx, ...]:
    if isinstance(spec, int):
        spec = [1] * spec
    total_weight = sum(spec)
    props.setdefault("className", "row")
    with div(**props):
        return tuple(
            div(
                className=f"col-lg-{p} {'col-12' if responsive else f'col-{p}'}",
                **column_props,
            )
            for w in spec
            if (p := f"{round(w / total_weight * 12)}")
        )


def image(
    src: str | np.ndarray,
    caption: str = None,
    alt: str = None,
    href: str = None,
    show_download_button: bool = False,
    **props,
):
    if isinstance(src, np.ndarray):
        from daras_ai.image_input import cv2_img_to_bytes

        if not src.shape:
            return
        # ensure image is not too large
        data = resize_img_scale(cv2_img_to_bytes(src), (128, 128))
        # convert to base64
        b64 = base64.b64encode(data).decode("utf-8")
        src = "data:image/png;base64," + b64
    if not src:
        return
    state.RenderTreeNode(
        name="img",
        props=dict(
            src=src,
            caption=dedent(caption),
            alt=alt or caption,
            href=href,
            **props,
        ),
    ).mount()
    if show_download_button:
        download_button(
            label='<i class="fa-regular fa-download"></i> Download', url=src
        )


def video(
    src: str,
    caption: str = None,
    autoplay: bool = False,
    show_download_button: bool = False,
):
    autoplay_props = {}
    if autoplay:
        autoplay_props = {
            "preload": "auto",
            "controls": True,
            "autoPlay": True,
            "loop": True,
            "muted": True,
            "playsInline": True,
        }

    if not src:
        return
    if isinstance(src, str):
        # https://muffinman.io/blog/hack-for-ios-safari-to-display-html-video-thumbnail/
        f = furl(src)
        f.fragment.args["t"] = "0.001"
        src = f.url
    state.RenderTreeNode(
        name="video",
        props=dict(src=src, caption=dedent(caption), **autoplay_props),
    ).mount()
    if show_download_button:
        download_button(
            label='<i class="fa-regular fa-download"></i> Download', url=src
        )


def audio(src: str, caption: str = None, show_download_button: bool = False):
    if not src:
        return
    state.RenderTreeNode(
        name="audio",
        props=dict(src=src, caption=dedent(caption)),
    ).mount()
    if show_download_button:
        download_button(
            label='<i class="fa-regular fa-download"></i> Download', url=src
        )


def text_area(
    label: str,
    value: str = "",
    height: int = 100,
    key: str = None,
    help: str = None,
    placeholder: str = None,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
    **props,
) -> str:
    style = props.setdefault("style", {})
    # if key:
    #     assert not value, "only one of value or key can be provided"
    # else:
    if not key:
        key = md5_values(
            "textarea",
            label,
            height,
            help,
            placeholder,
            label_visibility,
            not disabled or value,
        )
    value = str(state.session_state.setdefault(key, value) or "")
    if label_visibility != "visible":
        label = None
    if disabled:
        max_height = f"{height}px"
        rows = nrows_for_text(value, height, min_rows=1)
    else:
        max_height = "90vh"
        rows = nrows_for_text(value, height)
    style.setdefault("maxHeight", max_height)
    props.setdefault("rows", rows)
    state.RenderTreeNode(
        name="textarea",
        props=dict(
            name=key,
            label=dedent(label),
            defaultValue=value,
            help=help,
            placeholder=placeholder,
            disabled=disabled,
            **props,
        ),
    ).mount()
    return value or ""


def nrows_for_text(
    text: str,
    max_height_px: int,
    min_rows: int = 2,
    row_height_px: int = 30,
    row_width_px: int = 80,
) -> int:
    max_rows = max_height_px // row_height_px
    nrows = math.ceil(
        sum(len(line) / row_width_px for line in (text or "").strip().splitlines())
    )
    nrows = min(max(nrows, min_rows), max_rows)
    return nrows


def multiselect(
    label: str,
    options: typing.Sequence[T],
    format_func: typing.Callable[[T], typing.Any] = _default_format,
    key: str = None,
    help: str = None,
    allow_none: bool = False,
    *,
    disabled: bool = False,
) -> list[T]:
    if not options:
        return []
    options = list(options)
    if not key:
        key = md5_values("multiselect", label, options, help)
    value = state.session_state.get(key) or []
    if not isinstance(value, list):
        value = [value]
    value = [o if o in options else options[0] for o in value]
    if not allow_none and not value:
        value = [options[0]]
    state.session_state[key] = value
    state.RenderTreeNode(
        name="select",
        props=dict(
            name=key,
            label=dedent(label),
            help=help,
            isDisabled=disabled,
            isMulti=True,
            defaultValue=value,
            allow_none=allow_none,
            options=[
                {"value": option, "label": str(format_func(option))}
                for option in options
            ],
        ),
    ).mount()
    return value


def selectbox(
    label: str,
    options: typing.Iterable[T],
    format_func: typing.Callable[[T], typing.Any] = _default_format,
    key: str = None,
    help: str = None,
    *,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
    value: T = None,
    allow_none: bool = False,
    **props,
) -> T | None:
    if not options:
        return None
    if label_visibility != "visible":
        label = None
    options = list(options)
    if allow_none:
        options.insert(0, None)
    if not key:
        key = md5_values("select", label, options, help, label_visibility)
    value = state.session_state.setdefault(key, value)
    if value not in options:
        value = state.session_state[key] = options[0]
    state.RenderTreeNode(
        name="select",
        props=dict(
            name=key,
            label=dedent(label),
            help=help,
            isDisabled=disabled,
            defaultValue=value,
            options=[
                {"value": option, "label": str(format_func(option))}
                for option in options
            ],
            **props,
        ),
    ).mount()
    return value


def download_button(
    label: str,
    url: str,
    key: str = None,
    help: str = None,
    *,
    type: typing.Literal["primary", "secondary", "tertiary", "link"] = "secondary",
    disabled: bool = False,
    **props,
) -> bool:
    url = furl(url).remove(fragment=True).url
    return button(
        component="download-button",
        url=url,
        label=label,
        key=key,
        help=help,
        type=type,
        disabled=disabled,
        **props,
    )


def button(
    label: str,
    key: str = None,
    help: str = None,
    *,
    type: typing.Literal["primary", "secondary", "tertiary", "link"] = "secondary",
    disabled: bool = False,
    component: typing.Literal["download-button", "gui-button"] = "gui-button",
    **props,
) -> bool:
    """
    Example:
        st.button("Primary", key="test0", type="primary")
        st.button("Secondary", key="test1")
        st.button("Tertiary", key="test3", type="tertiary")
        st.button("Link Button", key="test3", type="link")
    """
    if not key:
        key = md5_values("button", label, help, type, props)
    className = f"btn-{type} " + props.pop("className", "")
    state.RenderTreeNode(
        name=component,
        props=dict(
            type="submit",
            value="yes",
            name=key,
            label=dedent(label),
            help=help,
            disabled=disabled,
            className=className,
            **props,
        ),
    ).mount()
    return bool(state.session_state.pop(key, False))


def anchor(
    label: str,
    href: str,
    *,
    type: typing.Literal["primary", "secondary", "tertiary", "link"] = "secondary",
    disabled: bool = False,
    unsafe_allow_html: bool = False,
    new_tab: bool = False,
    **props,
):
    className = f"btn btn-theme btn-{type} " + props.pop("className", "")
    style = props.pop("style", {})
    if disabled:
        style["pointerEvents"] = "none"
    if new_tab:
        props["target"] = "_blank"
    with tag("a", href=href, className=className, style=style, **props):
        markdown(dedent(label), unsafe_allow_html=unsafe_allow_html)


form_submit_button = button


def expander(label: str, *, expanded: bool = False, **props):
    node = state.RenderTreeNode(
        name="expander",
        props=dict(
            label=dedent(label),
            open=expanded,
            **props,
        ),
    )
    node.mount()
    return state.NestingCtx(node)


def file_uploader(
    label: str,
    accept: list[str] = None,
    accept_multiple_files=False,
    key: str = None,
    value: str | list[str] = None,
    upload_key: str = None,
    help: str = None,
    *,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
    upload_meta: dict = None,
    optional: bool = False,
) -> str | list[str]:
    if label_visibility != "visible":
        label = None
    key = upload_key or key
    if not key:
        key = md5_values(
            "file_uploader",
            label,
            accept,
            accept_multiple_files,
            help,
            label_visibility,
        )
    if optional:
        if not checkbox(
            label, value=bool(state.session_state.get(key, value)), disabled=disabled
        ):
            state.session_state.pop(key, None)
            return ""
        label = None
    value = state.session_state.setdefault(key, value)
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
            uploadMeta=upload_meta,
        ),
    ).mount()
    return value or ""


def json(value: typing.Any, expanded: bool = False, depth: int = 1):
    state.RenderTreeNode(
        name="json",
        props=dict(
            value=value,
            expanded=expanded,
            defaultInspectDepth=3 if expanded else depth,
        ),
    ).mount()


def data_table(file_url_or_cells: str | list):
    if isinstance(file_url_or_cells, str):
        file_url = file_url_or_cells
        return _node("data-table", fileUrl=file_url)
    else:
        cells = file_url_or_cells
        return _node("data-table-raw", cells=cells)


def table(df: "pd.DataFrame"):
    with tag("table", className="table table-striped table-sm"):
        with tag("thead"):
            with tag("tr"):
                for col in df.columns:
                    with tag("th", scope="col"):
                        html(dedent(col))
        with tag("tbody"):
            for row in df.itertuples(index=False):
                with tag("tr"):
                    for value in row:
                        with tag("td"):
                            html(dedent(str(value)))


def horizontal_radio(
    label: str,
    options: typing.Sequence[T],
    format_func: typing.Callable[[T], typing.Any] = _default_format,
    key: str = None,
    help: str = None,
    *,
    disabled: bool = False,
    checked_by_default: bool = True,
    label_visibility: LabelVisibility = "visible",
    **button_props,
) -> T | None:
    if not options:
        return None
    options = list(options)
    if not key:
        key = md5_values("horizontal_radio", label, options, help, label_visibility)
    value = state.session_state.get(key)
    if (key not in state.session_state or value not in options) and checked_by_default:
        value = options[0]
    state.session_state.setdefault(key, value)
    if label_visibility != "visible":
        label = None
    markdown(label)
    for option in options:
        if button(
            format_func(option),
            key=f"tab-{key}-{option}",
            type="primary",
            className="replicate-nav " + ("active" if value == option else ""),
            disabled=disabled,
            **button_props,
        ):
            state.session_state[key] = value = option
            state.experimental_rerun()
    return value


def custom_radio(
    label: str,
    options: typing.Sequence[T],
    format_func: typing.Callable[[T], typing.Any] = _default_format,
    key: str = None,
    help: str = None,
    *,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
    custom_input: int,
) -> T | None:
    if not key:
        key = md5_values("custom_radio", label, options, help, label_visibility)
    value = radio(
        label=label,
        options=options,
        format_func=format_func,
        key=key,
        help=help,
        disabled=disabled,
        label_visibility=label_visibility,
    )
    if custom_input:
        value = custom_input
    is_custom = value not in options
    custom = {
        "label": "Custom",
        "input": lambda label, key: number_input(
            label=label,
            min_value=1,
            max_value=60,
            step=1,
            key=key,
        ),
    }
    with div(className="d-flex", style={"gap": "1ch", "flex-direction": "row-reverse"}):
        with div(className="flex-grow-1"):
            state.session_state.setdefault(f"custom-{key}", value)
            val = custom["input"](label="", key=f"custom-{key}")
        with div():
            state.RenderTreeNode(
                name="input",
                props=dict(
                    type="radio",
                    name=key,
                    label=dedent(str(custom["label"])),
                    value=val,
                    defaultChecked=is_custom,
                    help=help,
                    disabled=disabled,
                ),
            ).mount()
    if type(options[0])(value) not in options:
        value = state.session_state[key] = state.session_state[f"custom-{key}"]
    return value


def radio(
    label: str,
    options: typing.Sequence[T],
    format_func: typing.Callable[[T], typing.Any] = _default_format,
    key: str = None,
    value: T = None,
    help: str = None,
    *,
    disabled: bool = False,
    checked_by_default: bool = True,
    label_visibility: LabelVisibility = "visible",
) -> T | None:
    if not options:
        return None
    options = list(options)
    if not key:
        key = md5_values("radio", label, options, help, label_visibility)
    value = state.session_state.setdefault(key, value)
    if value not in options and checked_by_default:
        value = state.session_state[key] = options[0]
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
    **props,
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
        **props,
    )
    return value or ""


def date_input(
    label: str,
    value: str | None = None,
    key: str = None,
    help: str = None,
    *,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
    **props,
) -> datetime | None:
    value = _input_widget(
        input_type="date",
        label=label,
        value=value,
        key=key,
        help=help,
        disabled=disabled,
        label_visibility=label_visibility,
        style=dict(
            border="1px solid hsl(0, 0%, 80%)",
            padding="0.375rem 0.75rem",
            borderRadius="0.25rem",
            margin="0 0.5rem 0 0.5rem",
        ),
        **props,
    )
    try:
        return datetime.strptime(value, "%Y-%m-%d") if value else None
    except ValueError:
        return None


def password_input(
    label: str,
    value: str = "",
    max_chars: str = None,
    key: str = None,
    help: str = None,
    *,
    placeholder: str = None,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
    **props,
) -> str:
    value = _input_widget(
        input_type="password",
        label=label,
        value=value,
        key=key,
        help=help,
        disabled=disabled,
        label_visibility=label_visibility,
        maxLength=max_chars,
        placeholder=placeholder,
        **props,
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
    className: str = "",
    **props,
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
        className=className,
        **props,
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
    className: str = "",
    **kwargs,
) -> typing.Any:
    # if key:
    #     assert not value, "only one of value or key can be provided"
    # else:
    if not key:
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
            "className": className,
            **kwargs,
        },
    ).mount()
    return value


def breadcrumbs(divider: str = "/", **props) -> state.NestingCtx:
    style = props.pop("style", {}) | {"--bs-breadcrumb-divider": f"'{divider}'"}
    with tag("nav", style=style, **props):
        return tag("ol", className="breadcrumb mb-0")


def breadcrumb_item(inner_html: str, link_to: str | None = None, **props):
    className = "breadcrumb-item " + props.pop("className", "")
    with tag("li", className=className, **props):
        if link_to:
            with tag("a", href=link_to):
                html(inner_html)
        else:
            html(inner_html)


def plotly_chart(figure_or_data, **kwargs):
    data = (
        figure_or_data.to_plotly_json()
        if hasattr(figure_or_data, "to_plotly_json")
        else figure_or_data
    )
    state.RenderTreeNode(
        name="plotly-chart",
        props=dict(
            chart=data,
            args=kwargs,
        ),
    ).mount()


def dedent(text: str | None) -> str | None:
    if not text:
        return text
    return textwrap.dedent(text)


def js(src: str, **kwargs):
    state.RenderTreeNode(
        name="script",
        props=dict(
            src=src,
            args=kwargs,
        ),
    ).mount()
