import base64
import html as html_lib
import math
import textwrap
import typing
from datetime import datetime, timezone

from furl import furl
from gooey_gui import core

T = typing.TypeVar("T")
LabelVisibility = typing.Literal["visible", "collapsed"]
TooltipPlacement = typing.Literal["left", "right", "top", "bottom", "auto"]

BLANK_OPTION = "———"


def _default_format(value: typing.Any) -> str:
    if value is None:
        return BLANK_OPTION
    return str(value)


def dummy(*args, **kwargs):
    return core.NestingCtx()


spinner = dummy
set_page_config = dummy
form = dummy
dataframe = dummy


def countdown_timer(
    end_time: datetime,
    delay_text: str,
) -> core.NestingCtx:
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


def div(**props) -> core.NestingCtx:
    return tag("div", **props)


def link(*, to: str, **props) -> core.NestingCtx:
    return _node("Link", to=to, **props)


def tag(tag_name: str, **props) -> core.NestingCtx:
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


def center(direction="flex-column", className="") -> core.NestingCtx:
    return div(
        className=f"d-flex justify-content-center align-items-center text-center {direction} {className}"
    )


def newline():
    html("<br/>")


def markdown(
    body: str | None,
    *,
    line_clamp: int = None,
    unsafe_allow_html=False,
    **props,
):
    if body is None:
        return _node("markdown", body="", **props)
    if not unsafe_allow_html:
        body = html_lib.escape(body)
    props["className"] = (
        props.get("className", "") + " gui-html-container gui-md-container"
    )
    return _node(
        "markdown",
        body=dedent(body).strip(),
        lineClamp=line_clamp,
        **props,
    )


def _node(nodename: str, **props):
    node = core.RenderTreeNode(name=nodename, props=props)
    node.mount()
    return core.NestingCtx(node)


def styled(css: str) -> core.NestingCtx:
    css = dedent(css).strip()
    className = "gui-" + core.md5_values(css)
    selector = "." + className
    css = css.replace("&", selector)
    core.add_styles(className, css)
    return _node("", className=className)


def text(body: str, **props):
    core.RenderTreeNode(
        name="pre",
        props=dict(body=dedent(body), **props),
    ).mount()


def error(
    body: str,
    icon: str = "🔥",
    *,
    unsafe_allow_html=False,
    color="rgba(255, 108, 108, 0.2)",
    **props,
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
            markdown(dedent(body), unsafe_allow_html=unsafe_allow_html, **props)


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


def tabs(labels: list[str]) -> list[core.NestingCtx]:
    parent = core.RenderTreeNode(
        name="tabs",
        children=[
            core.RenderTreeNode(
                name="tab",
                props=dict(label=dedent(label)),
            )
            for label in labels
        ],
    ).mount()
    return [core.NestingCtx(tab) for tab in parent.children]


def controllable_tabs(labels: list[str], key: str) -> tuple[list[core.NestingCtx], int]:
    index = core.session_state.get(key, 0)
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
            core.session_state[key] = index = i
            core.rerun()
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
) -> tuple[core.NestingCtx, ...]:
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
    src,
    caption: str = None,
    alt: str = None,
    href: str = None,
    show_download_button: bool = False,
    **props,
):
    try:
        import numpy as np

        is_np_img = isinstance(src, np.ndarray)
    except ImportError:
        is_np_img = False
    if is_np_img:
        if not src.shape:
            return
        # ensure image is not too large
        data = _export_cv2_img(src, 128)
        # convert to base64
        b64 = base64.b64encode(data).decode("utf-8")
        src = "data:image/png;base64," + b64
    if not src:
        return
    core.RenderTreeNode(
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


def _export_cv2_img(img, size: int) -> bytes:
    """
    Resize the image to the given size, keeping the aspect ratio.
    """
    import cv2

    h, w = img.shape[:2]
    new_h = size
    new_w = int(w * new_h / h)
    img = cv2.resize(img, (new_w, new_h))
    data = cv2.imencode(".png", img)[1].tostring()
    return data


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
    core.RenderTreeNode(
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
    core.RenderTreeNode(
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
    height: int = 500,
    key: str = None,
    help: str | None = None,
    tooltip_placement: TooltipPlacement | None = None,
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
        key = core.md5_values(
            "textarea",
            label,
            height,
            help,
            placeholder,
            label_visibility,
            not disabled or value,
        )
    value = str(core.session_state.setdefault(key, value) or "")
    if label_visibility != "visible":
        label = None
    if disabled:
        max_height = f"{height}px"
        rows = nrows_for_text(value, height)
    else:
        max_height = "50vh"
        rows = nrows_for_text(value, height)
    style.setdefault("maxHeight", max_height)
    props.setdefault("rows", rows)
    core.RenderTreeNode(
        name="textarea",
        props=dict(
            name=key,
            label=dedent(label),
            defaultValue=value,
            help=help,
            tooltipPlacement=tooltip_placement,
            placeholder=placeholder,
            disabled=disabled,
            **props,
        ),
    ).mount()
    return value or ""


def code_editor(
    value: str = "",
    key: str = None,
    label: str = None,
    label_visibility: LabelVisibility = "visible",
    **props,
) -> typing.Any:
    value = str(core.session_state.setdefault(key, value) or "")
    if label_visibility != "visible":
        label = None
    core.RenderTreeNode(
        name="code-editor",
        props=dict(
            name=key,
            defaultValue=value,
            label=dedent(label),
            **props,
        ),
    ).mount()
    return value or ""


def nrows_for_text(
    text: str,
    max_height_px: int,
    min_rows: int = 1,
    row_height_px: int = 30,
    row_width_px: int = 70,
) -> int:
    max_rows = max_height_px // row_height_px
    nrows = math.ceil(
        sum(
            math.ceil(len(line) / row_width_px)
            for line in (text or "").splitlines(keepends=True)
        )
    )
    nrows = min(max(nrows, min_rows), max_rows)
    return nrows


def multiselect(
    label: str,
    options: typing.Sequence[T],
    format_func: typing.Callable[[T], typing.Any] = _default_format,
    key: str = None,
    help: str | None = None,
    tooltip_placement: TooltipPlacement | None = None,
    allow_none: bool = False,
    *,
    disabled: bool = False,
) -> list[T]:
    if not options:
        return []
    options = list(options)
    if not key:
        key = core.md5_values("multiselect", label, options, help)
    value = core.session_state.get(key) or []
    if not isinstance(value, list):
        value = [value]
    value = [o for o in value if o in options]
    if not allow_none and not value:
        value = [options[0]]
    core.session_state[key] = value
    core.RenderTreeNode(
        name="select",
        props=dict(
            name=key,
            label=dedent(label),
            help=help,
            tooltipPlacement=tooltip_placement,
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
    help: str | None = None,
    tooltip_placement: TooltipPlacement | None = None,
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
        key = core.md5_values("select", label, options, help, label_visibility)
    value = core.session_state.setdefault(key, value)
    if value not in options:
        value = core.session_state[key] = options[0]
    core.RenderTreeNode(
        name="select",
        props=dict(
            name=key,
            label=dedent(label),
            help=help,
            tooltipPlacement=tooltip_placement,
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
    help: str | None = None,
    tooltip_placement: TooltipPlacement | None = None,
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
        tooltip_placement=tooltip_placement,
        type=type,
        disabled=disabled,
        **props,
    )


def button(
    label: str,
    key: str = None,
    help: str | None = None,
    tooltip_placement: TooltipPlacement | None = None,
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
        key = core.md5_values("button", label, help, type, props)
    className = f"btn btn-theme btn-{type} " + props.pop("className", "")
    core.RenderTreeNode(
        name=component,
        props=dict(
            type="submit",
            value="yes",
            name=key,
            label=dedent(label),
            disabled=disabled,
            className=className,
            **props,
        ),
    ).mount()
    return bool(core.session_state.pop(key, False))


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


def expander(label: str, *, expanded: bool = False, key: str = None, **props):
    node = core.RenderTreeNode(
        name="expander",
        props=dict(
            label=dedent(label),
            open=expanded,
            name=key or core.md5_values(label, expanded, props),
            **props,
        ),
    )
    node.mount()
    return core.NestingCtx(node)


def file_uploader(
    label: str,
    accept: list[str] = None,
    accept_multiple_files=False,
    key: str = None,
    value: str | list[str] = None,
    upload_key: str = None,
    help: str | None = None,
    tooltip_placement: TooltipPlacement | None = None,
    *,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
    upload_meta: dict = None,
    optional: bool = False,
) -> str | list[str] | None:
    from .input_widgets import checkbox

    if label_visibility != "visible":
        label = None
    key = upload_key or key
    if not key:
        key = core.md5_values(
            "file_uploader",
            label,
            accept,
            accept_multiple_files,
            help,
            label_visibility,
        )
    if optional:
        if not checkbox(
            label,
            value=bool(core.session_state.get(key, value)),
            disabled=disabled,
            help=help,
        ):
            core.session_state.pop(key, None)
            return None
        label = None
    value = core.session_state.setdefault(key, value)
    if not value:
        if accept_multiple_files:
            value = []
        else:
            value = None
    core.session_state[key] = value
    core.RenderTreeNode(
        name="input",
        props=dict(
            type="file",
            name=key,
            label=dedent(label),
            help=help,
            tooltipPlacement=tooltip_placement,
            disabled=disabled,
            accept=accept,
            multiple=accept_multiple_files,
            defaultValue=value,
            uploadMeta=upload_meta,
        ),
    ).mount()
    return value


def json(value: typing.Any, expanded: bool = False, depth: int = 1, **props):
    core.RenderTreeNode(
        name="json",
        props=dict(
            value=value,
            expanded=expanded,
            defaultInspectDepth=3 if expanded else depth,
            **props,
        ),
    ).mount()


def data_table(file_url_or_cells: str | list, **props):
    if isinstance(file_url_or_cells, str):
        props["fileUrl"] = file_url_or_cells
    else:
        props["cells"] = file_url_or_cells
    return _node("data-table", **props)


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
    *,
    key: str = None,
    help: str | None = None,
    tooltip_placement: TooltipPlacement | None = None,
    value: T = None,
    disabled: bool = False,
    checked_by_default: bool = True,
    label_visibility: LabelVisibility = "visible",
    **button_props,
) -> T | None:
    if not options:
        return None
    options = list(options)
    if not key:
        key = core.md5_values(
            "horizontal_radio", label, options, help, label_visibility
        )
    value = core.session_state.setdefault(key, value)
    if value not in options and checked_by_default:
        value = core.session_state[key] = options[0]
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
            core.session_state[key] = value = option
            core.rerun()
    return value


def radio(
    label: str,
    options: typing.Sequence[T],
    format_func: typing.Callable[[T], typing.Any] = _default_format,
    key: str = None,
    value: T = None,
    help: str | None = None,
    tooltip_placement: TooltipPlacement | None = None,
    *,
    disabled: bool = False,
    checked_by_default: bool = True,
    label_visibility: LabelVisibility = "visible",
    **props,
) -> T | None:
    if not options:
        return None
    options = list(options)
    if not key:
        key = core.md5_values("radio", label, options, help, label_visibility)
    value = core.session_state.setdefault(key, value)
    if value not in options and checked_by_default:
        value = core.session_state[key] = options[0]
    if label_visibility != "visible":
        label = None
    markdown(label)
    for option in options:
        core.RenderTreeNode(
            name="input",
            props=dict(
                type="radio",
                name=key,
                label=dedent(str(format_func(option))),
                value=option,
                defaultChecked=bool(value == option),
                help=help,
                tooltipPlacement=tooltip_placement,
                disabled=disabled,
                **props,
            ),
        ).mount()
    return value


def breadcrumbs(divider: str = "/", **props) -> core.NestingCtx:
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
    core.RenderTreeNode(
        name="plotly-chart",
        props=dict(
            chart=data,
            args=kwargs,
        ),
    ).mount()


def popover(
    *, placement: TooltipPlacement | None = None, **props
) -> tuple[core.NestingCtx, core.NestingCtx]:
    content = core.RenderTreeNode(name="content")

    popover = core.RenderTreeNode(
        name="popover",
        props=props | dict(content=content.children, placement=placement),
    )
    popover.mount()

    return core.NestingCtx(popover), core.NestingCtx(content)


def dedent(text: str | None) -> str | None:
    if not text:
        return text
    return textwrap.dedent(text)


def js(src: str, **kwargs):
    core.RenderTreeNode(
        name="script",
        props=dict(
            src=src,
            args=kwargs,
        ),
    ).mount()


def switch(
    label: str,
    value: bool = False,
    key: str = None,
    help: str | None = None,
    tooltip_placement: TooltipPlacement | None = None,
    *,
    disabled: bool = False,
    size: typing.Literal["small", "large"] = "large",
    label_visibility: LabelVisibility = "visible",
    **props,
) -> bool:
    if not key:
        key = core.md5_values("input", "switch", label, help, label_visibility)
    value = core.session_state.setdefault(key, value)
    if label_visibility != "visible":
        label = None
    core.RenderTreeNode(
        name="switch",
        props={
            "name": key,
            "label": dedent(label),
            "defaultChecked": value,
            "help": help,
            "tooltipPlacement": tooltip_placement,
            "disabled": disabled,
            "size": size,
            **props,
        },
    ).mount()
    return bool(value)


def tooltip(
    content: str = "",
    *,
    placement: TooltipPlacement | None = None,
    **props,
) -> core.NestingCtx:
    tooltip = core.RenderTreeNode(
        name="tooltip",
        props={
            "content": content,
            "placement": placement,
            **props,
        },
    )
    tooltip.mount()
    return core.NestingCtx(tooltip)
