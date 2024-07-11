import enum
import typing
from typing import TypeVar, Type

import gooey_ui as st
from daras_ai_v2.grid_layout_widget import grid_layout
from gooey_ui import BLANK_OPTION

E = TypeVar("E", bound=Type[enum.Enum])


def enum_multiselect(
    enum_cls: E,
    key: str,
    label: str = "",
    checkboxes=True,
    allow_none=True,
):
    try:
        deprecated = enum_cls._deprecated()
    except AttributeError:
        deprecated = set()
    enums = []
    value = st.session_state.get(key, [])
    for e in enum_cls:
        if e in deprecated and e.name not in value:
            continue
        enums.append(e)
    enum_names = [e.name for e in enums]

    if checkboxes:
        if label:
            st.caption(label)
        selected = set(st.session_state.get(key, []))
        ret_val = []

        def render(name):
            inner_key = f"{key} => {name}"
            if inner_key not in st.session_state:
                st.session_state[inner_key] = name in selected

            st.checkbox(_format_func(enum_cls)(name), key=inner_key)

            if st.session_state.get(inner_key):
                ret_val.append(name)

        grid_layout(2, enum_names, render, separator=False)

        st.session_state[key] = ret_val
        return ret_val
    else:
        return st.multiselect(
            options=enum_names,
            format_func=_format_func(enum_cls),
            label=label,
            key=key,
            allow_none=allow_none,
        )


def enum_selector(
    enum_cls: E,
    label: str = "",
    allow_none: bool = False,
    use_selectbox: bool = False,
    exclude: list[E] | None = None,
    **kwargs,
) -> str:
    try:
        deprecated = enum_cls._deprecated()
    except AttributeError:
        deprecated = set()
    enums = [e for e in enum_cls if not e in deprecated]
    options = [e.name for e in enums]
    if exclude:
        options = [o for o in options if o not in exclude]
    if allow_none:
        options.insert(0, None)
    if use_selectbox:
        widget = st.selectbox
    else:
        widget = st.radio
    kwargs.setdefault("format_func", _format_func(enum_cls))
    return widget(
        **kwargs,
        options=options,
        label=label,
    )


def _format_func(enum_cls: E) -> typing.Callable[[str], str]:
    def _format(k):
        if not k:
            return BLANK_OPTION
        e = enum_cls[k]
        try:
            return e.label
        except AttributeError:
            return e.value

    return _format
