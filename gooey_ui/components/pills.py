import html

import gooey_ui as gui


def pill(
    title: str,
    *,
    unsafe_allow_html: bool = False,
    className: str = "",
    **props,
):
    className = "text-sm bg-light rounded-pill px-2 py-1 " + className
    with gui.tag("span", className=className, **props):
        gui.html(
            title if unsafe_allow_html else html.escape(title),
        )
