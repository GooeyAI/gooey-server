import gooey_gui as gui


def html_spinner(text: str, scroll_into_view=True):
    gui.html(
        # language=HTML
        f"""
<div class="gooey-spinner-top" style="padding-top: 8px; padding-bottom: 8px;">
    <div class="gooey-spinner"></div>
    <div class="gooey-spinner-text">{text}</div>
</div>
        """
    )

    if scroll_into_view:
        gui.js(
            # language=JavaScript
            """document.querySelector(".gooey-spinner-top").scrollIntoView()"""
        )
