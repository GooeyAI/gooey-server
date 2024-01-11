import enum
import typing
from typing import TypeVar, Type

import gooey_ui as st
from daras_ai_v2.grid_layout_widget import grid_layout

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

    if checkboxes:
        if label:
            st.write(label)
        selected = set(st.session_state.get(key, []))

        def render(e):
            inner_key = f"{key} => {e.name}"
            if inner_key not in st.session_state:
                st.session_state[inner_key] = e.name in selected

            st.checkbox(_format_func(enum_cls)(e.name), key=inner_key)

            if st.session_state.get(inner_key):
                selected.add(e.name)
            else:
                selected.discard(e.name)

        grid_layout(2, enums, render, separator=False)
        st.session_state[key] = list(selected)

        return selected
    else:
        return st.multiselect(
            options=[e.name for e in enums],
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
    return widget(
        **kwargs,
        options=options,
        format_func=_format_func(enum_cls),
        label=label,
    )


def _format_func(enum_cls: E) -> typing.Callable[[str], str]:
    def _format(k):
        if not k:
            return "———"
        e = enum_cls[k]
        try:
            return e.label
        except AttributeError:
            return e.value

    return _format
