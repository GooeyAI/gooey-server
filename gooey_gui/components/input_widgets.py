import base64
import html as html_lib
import math
import textwrap
import typing
from datetime import datetime, timezone

from furl import furl
from gooey_gui import core
from loguru import logger

from .common import LabelVisibility, TooltipPlacement, dedent


def text_input(
    label: str,
    value: str = "",
    max_chars: str = None,
    key: str = None,
    help: str | None = None,
    tooltip_placement: TooltipPlacement | None = None,
    *,
    placeholder: str = None,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
    **props,
) -> str:
    value = _html_input(
        "text",
        label=label,
        value=value,
        key=key,
        help=help,
        tooltip_placement=tooltip_placement,
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
    help: str | None = None,
    tooltip_placement: TooltipPlacement | None = None,
    *,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
    **props,
) -> datetime | None:
    value = _html_input(
        "date",
        label=label,
        value=value,
        key=key,
        help=help,
        tooltip_placement=tooltip_placement,
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
    help: str | None = None,
    tooltip_placement: TooltipPlacement | None = None,
    *,
    placeholder: str = None,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
    **props,
) -> str:
    value = _html_input(
        "password",
        label=label,
        value=value,
        key=key,
        help=help,
        tooltip_placement=tooltip_placement,
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
    help: str | None = None,
    tooltip_placement: TooltipPlacement | None = None,
    *,
    disabled: bool = False,
) -> float:
    value = _html_input(
        "range",
        label=label,
        value=value,
        key=key,
        help=help,
        tooltip_placement=tooltip_placement,
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
    help: str | None = None,
    tooltip_placement: TooltipPlacement | None = None,
    *,
    disabled: bool = False,
) -> float:
    value = _html_input(
        "number",
        inputMode="decimal",
        label=label,
        value=value,
        key=key,
        help=help,
        tooltip_placement=tooltip_placement,
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
    help: str | None = None,
    tooltip_placement: TooltipPlacement | None = None,
    *,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
    **props,
) -> bool:
    value = _html_input(
        "checkbox",
        label=label,
        value=value,
        key=key,
        help=help,
        tooltip_placement=tooltip_placement,
        disabled=disabled,
        label_visibility=label_visibility,
        default_value_attr="defaultChecked",
        **props,
    )
    return bool(value)


def _html_input(
    input_type: str,
    /,
    *,
    label: str,
    value: typing.Any = None,
    key: str = None,
    help: str | None = None,
    tooltip_placement: TooltipPlacement | None = None,
    disabled: bool = False,
    label_visibility: LabelVisibility = "visible",
    default_value_attr: str = "defaultValue",
    **kwargs,
) -> typing.Any:
    if not key:
        key = core.md5_values("input", input_type, label, help, label_visibility)
    value = core.session_state.setdefault(key, value)
    if label_visibility != "visible":
        label = None
    core.RenderTreeNode(
        name="input",
        props={
            "type": input_type,
            "name": key,
            "label": dedent(label),
            default_value_attr: value,
            "help": help,
            "tooltipPlacement": tooltip_placement,
            "disabled": disabled,
            **kwargs,
        },
    ).mount()
    return value
