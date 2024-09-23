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
    style: dict[str, str] | None = None,
    className: str = "",
    type: typing.Literal["primary", "secondary", "tertiary", "link"] = "primary",
    key: str | None = None,
) -> bool:
    key = key or "copy-to-clipboard-btn"
    pressed = gui.button(
        label,
        id=key,
        className=className,
        style=style,
        type=type,
        **{"data-clipboard-text": value},
    )
    if pressed:
        gui.js(
            # language="javascript"
            f"""
            copyToClipboard(document.getElementById("{escape(key)}"));
            """
        )
    return pressed
