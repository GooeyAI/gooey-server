import gooey_gui as gui


def html_spinner(text: str, scroll_into_view=True):
    with gui.div(className="gooey-spinner-top d-flex align-items-center gap-2 py-4"):
        gui.div(className="gooey-spinner p-3")
        with (
            gui.div(className="gooey-spinner-text"),
            gui.styled("& p { margin-bottom: 1px }"),
        ):
            gui.write(text)

    if scroll_into_view:
        gui.js(
            # language=JavaScript
            """
            let elem = document.querySelector(".gooey-spinner-top");
            if (!elem) return;
            if (elem.scrollIntoViewIfNeeded) {
                elem.scrollIntoViewIfNeeded(false);
            } else {
                elem.scrollIntoView({ behavior: "smooth", block: "start" });
            }
            """
        )
