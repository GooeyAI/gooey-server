import json

import gooey_gui as gui


def html_spinner(text: str):
    gui.html(
        # language=HTML
        f"""
<div class="gooey-spinner-top" style="padding-top: 8px; padding-bottom: 8px;">
    <div class="gooey-spinner"></div>
    <div class="gooey-spinner-text">{text}</div>
</div>
        """
    )


def scroll_into_view(selector: str):
    gui.js("document.querySelector(%s).scrollIntoView();" % json.dumps(selector))
