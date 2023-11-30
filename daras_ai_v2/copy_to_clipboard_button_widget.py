import typing
import gooey_ui as gui

# language="html"
copy_to_clipboard_scripts = """
<script>
function copyToClipboard(button) {
    navigator.clipboard.writeText(button.getAttribute("data-clipboard-text"));
    const original = button.textContent;
    button.textContent = "✅ Copied";
    setTimeout(() => {
        button.textContent = original;
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
    onClick="copyToClipboard(this);"
    style="{style}"
    data-clipboard-text={value!r}>
    {label}
</button>
        """,
    )
