import enum
from typing import TypeVar, Type

import streamlit as st

E = TypeVar("E", bound=Type[enum.Enum])


def enum_multiselect(
    enum_cls: E,
    key: str,
    label: str = "",
):
    label = label or enum_cls.name
    # return st.multiselect(
    #     **kwargs,
    #     options=[e.name for e in enum_cls],
    #     format_func=lambda k: enum_cls[k].value,
    #     label=label,
    # )

    st.write(label)
    selected = set(st.session_state.get(key, []))
    col1, col2 = st.columns(2)
    for idx, e in enumerate(enum_cls):
        indiv_key = f"__{key}_{e.name}"
        if indiv_key not in st.session_state:
            st.session_state[indiv_key] = e.name in selected
        if idx % 2 == 0:
            col = col1
        else:
            col = col2
        with col:
            st.checkbox(e.value, key=indiv_key)
        if st.session_state.get(indiv_key):
            selected.add(e.name)
        else:
            try:
                selected.remove(e.name)
            except KeyError:
                pass
    st.session_state[key] = list(selected)


def enum_selector(
    enum_cls: E,
    label: str = "",
    **kwargs,
) -> str:
    label = label or enum_cls.name
    return st.radio(
        **kwargs,
        options=[e.name for e in enum_cls],
        format_func=lambda k: enum_cls[k].value,
        label=label,
    )
