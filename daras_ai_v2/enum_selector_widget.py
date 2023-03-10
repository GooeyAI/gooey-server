import enum
from typing import TypeVar, Type

import streamlit as st

from daras_ai_v2.grid_layout_widget import grid_layout

E = TypeVar("E", bound=Type[enum.Enum])


def enum_multiselect(
    enum_cls: E,
    key: str,
    label: str = "",
    checkboxes=True,
):
    if checkboxes:
        if label:
            st.write(label)
        selected = set(st.session_state.get(key, []))

        def render(e):
            inner_key = f"{key} => {e.name}"
            if inner_key not in st.session_state:
                st.session_state[inner_key] = e.name in selected

            st.checkbox(e.value, key=inner_key)

            if st.session_state.get(inner_key):
                selected.add(e.name)
            else:
                selected.discard(e.name)

        grid_layout(2, enum_cls, render, separator=None)
        st.session_state[key] = list(selected)

        return selected
    else:
        return st.multiselect(
            options=[e.name for e in enum_cls],
            format_func=lambda k: enum_cls[k].value,
            label=label,
        )


def enum_selector(
    enum_cls: E,
    label: str = "",
    allow_none: bool = False,
    use_selectbox: bool = False,
    **kwargs,
) -> str:
    label = label or enum_cls.__name__
    options = [e.name for e in enum_cls]
    if allow_none:
        options.insert(0, None)
    if use_selectbox:
        widget = st.selectbox
    else:
        widget = st.radio
    return widget(
        **kwargs,
        options=options,
        format_func=lambda k: enum_cls[k].value if k else "———",
        label=label,
    )
