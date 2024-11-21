import json
import typing
from html import escape

import gooey_gui as gui
from daras_ai_v2 import icons


# language="html"
copy_to_clipboard_scripts = """
<script>
function copyToClipboard(button) {
    navigator.clipboard.writeText(button.getAttribute("data-clipboard-text"));
    const original = button.innerHTML;
    const originalStyleWidth = button.style.width || "";

    if (button.offsetWidth > 90) {
        // 90 is roughly an estimate for pixel-width of the text we want to insert.
        // if the button was already big enough to show the new text, we want to stay that size.
        button.style.width = button.offsetWidth + "px";
    }
    button.innerHTML = `Copied %(copied_icon)s`;

    setTimeout(() => {
        button.innerHTML = original;
        button.style.width = originalStyleWidth;
    }, 2000);
}
</script>
""" % {
    "copied_icon": icons.check
}


def copy_to_clipboard_button(
    label: str,
    *,
    value: str,
    style: str = "",
    className: str = "",
    type: typing.Literal["primary", "secondary", "tertiary", "link"] = "primary",
):
    return gui.html(
        # language="html"
        f"""
<button
    type="button"
    class="btn btn-theme btn-{type} {className}"
    onclick="copyToClipboard(this);"
    style="{style}"
    data-clipboard-text="{escape(value)}">
    {label}
</button>
        """,
    )


def copy_text_to_clipboard(text):
    gui.js(
        # language="javascript"
        f"""
        navigator.clipboard.writeText({json.dumps(text)});
        """
    )
