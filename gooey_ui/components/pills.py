import html
from typing import Literal

import gooey_ui as gui


def pill(
    title: str,
    *,
    unsafe_allow_html: bool = False,
    type: Literal["primary", "secondary", "light", "dark", None] = "light",
    className: str = "",
    **props,
):
    className = className + f" badge rounded-pill"
    if type:
        className += f" text-bg-{type}"

    with gui.tag("span", className=className, **props):
        gui.html(
            title if unsafe_allow_html else html.escape(title),
        )
