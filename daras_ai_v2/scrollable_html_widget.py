from html_sanitizer import Sanitizer
import gooey_gui as gui


def scrollable_html(
    body: str,
    *,
    height=500,
):
    with gui.div(
        style=dict(maxHeight=height),
        className="gooey-output-text",
    ):
        gui.html(Sanitizer().sanitize(body))
