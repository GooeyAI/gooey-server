import gooey_ui as gui

# language="html"
copy_to_clipboard_scripts = """
<script>
function copyToClipboard(button) {
    navigator.clipboard.writeText(button.getAttribute("data-clipboard-text"));
    let old = button.textContent;
    button.textContent = "✅ Copied";
    setTimeout(() => {
        button.textContent = old;
     }, 2000);
}
</script>
"""


def copy_to_clipboard_button(
    label: str,
    *,
    value: str,
    style: str = "",
):
    return gui.html(
        # language="html"
        f"""
<button 
    type="button"
    class="btn btn-theme" 
    onclick="copyToClipboard(this)"
    style="{style}" 
    data-clipboard-text={value!r}> 
    {label}
</button>
        """,
    )
