import json
import typing
from html import escape

import gooey_gui as gui

# language="html"
copy_to_clipboard_scripts = """
<script>
function copyToClipboard(button) {
    navigator.clipboard.writeText(button.getAttribute("data-clipboard-text"));
    const original = button.innerHTML;
    button.textContent = "✅ Copied";
    setTimeout(() => {
        button.innerHTML = original;
    }, 2000);
}
</script>
"""


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
