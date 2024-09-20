import random

import gooey_gui as gui


def text_outputs(
    label: str,
    *,
    key: str = None,
    value: str | list = None,
    height: int = 200,
):
    value = value or gui.session_state.get(key)
    match value:
        case str():
            text_output(label, height=height, value=value)
        case list():
            gui.write(label)
            for idx, text in enumerate(value):
                text_output(
                    label,
                    label_visibility="collapsed",
                    height=height,
                    idx=idx,
                    value=str(text),
                )
        case _:
            gui.div()


def text_output(label: str, *, value: str, height: int = 200, idx: int = 0, **kwargs):
    gui.text_area(
        label,
        help=f"output text {idx + 1} #{random.random()}",
        disabled=True,
        value=value,
        height=height,
        **kwargs,
    )
