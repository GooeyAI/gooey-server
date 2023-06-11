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

// get all disabled textareas
const disabledTextareas = Array.from(document.querySelectorAll('textarea:disabled'));

disabledTextareas.forEach((textarea) => {
    // create a wrapper div
    const wrapper = document.createElement('div');
    wrapper.className = 'textarea-wrapper';

    // create a copy button
    const button = document.createElement('button');
    button.textContent = 'Copy';
    button.addEventListener('click', () => {
        navigator.clipboard.writeText(textarea.value)
            .then(() => console.log('Copied to clipboard'))
            .catch(err => console.error('Failed to copy text: ', err));
    });

    // wrap textarea with div
    textarea.parentNode.insertBefore(wrapper, textarea);
    wrapper.appendChild(textarea);
    // add copy button into the wrapper
    wrapper.appendChild(button);
});
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
