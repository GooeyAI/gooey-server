from gooey_ui import html

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
    height: int = 35,
):
    html(
        # language="html"
        f"""
<button 
    type="button" 
    onclick="copyToClipboard(this)" 
    data-clipboard-text={value!r} 
    style="{style}; height: {height}px">
    {label}
</button>
        """
    )
