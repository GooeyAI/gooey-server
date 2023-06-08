import gooey_ui as gui


def scrollable_html(
    text: str,
    *,
    height=500,
):
    with gui.div(
        style=dict(maxHeight=height),
        className="gooey-output-text",
    ):
        with gui.tag("p"):
            gui.html(text)
