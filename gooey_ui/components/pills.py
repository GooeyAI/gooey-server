import html
from typing import Literal

import gooey_ui as gui


def pill(
    title: str,
    *,
    unsafe_allow_html: bool = False,
    text_bg: Literal["primary", "secondary", "light", "dark", None] = "light",
    className: str = "",
    **props,
):
    if not unsafe_allow_html:
        title = html.escape(title)

    className += f" badge rounded-pill"
    if text_bg:
        className += f" text-bg-{text_bg}"

    with gui.tag("span", className=className):
        gui.html(title, **props)
