import random

import streamlit2 as st


def text_outputs(
    label: str,
    *,
    key: str = None,
    value: str = None,
    height: int = 200,
):
    value = value or st.session_state.get(key)
    match value:
        case str():
            text_output(label, height=height, value=value)
        case list():
            st.write(label)
            for idx, text in enumerate(value):
                text_output(
                    label,
                    label_visibility="collapsed",
                    height=height,
                    idx=idx,
                    value=text,
                )
        case _:
            st.div()


def text_output(label: str, *, value: str, height: int = 200, idx: int = 0, **kwargs):
    st.text_area(
        label,
        help=f"output text {idx + 1} #{random.random()}",
        disabled=True,
        value=value,
        height=height,
        **kwargs,
    )
