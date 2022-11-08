import enum
from typing import TypeVar, Type, Optional

import streamlit as st
from streamlit.runtime.state import WidgetCallback, WidgetArgs, WidgetKwargs
from streamlit.type_util import LabelVisibility, Key

E = TypeVar("E", bound=Type[enum.Enum])


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
