import secrets

from streamlit2 import html

st_like_btn_css_html = """
<style>
    .streamlit-like-btn, 
    .streamlit-like-btn:visited, 
    .streamlit-like-btn:hover, 
    .streamlit-like-btn:active {
        cursor: pointer;
        font-family: Arial, "Source Sans Pro", sans-serif;
        font-size: 15px;
        text-decoration: none !important;
        color: white !important;
        display: inline-flex;
        -webkit-box-align: center;
        align-items: center;
        -webkit-box-pack: center;
        justify-content: center;
        font-weight: 400;
        padding: 0.25rem 0.75rem;
        border-radius: 0.25rem;
        margin: 0px;
        line-height: 1.6;
        width: auto;
        user-select: none;
        background-color: rgb(8, 8, 8);
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
</style>
"""


def copy_to_clipboard_button(
    label: str,
    *,
    value: str,
    message: str = "✅ Copied",
    timeout_ms: float = 2000,
    style: str = "",
    height: int = 35,
):
    button_id = secrets.token_urlsafe(8)

    widget_css = (
        """
        <style>
            body {
                margin: 0;
            }
        </style>
        """
        + st_like_btn_css_html
    )

    widget_html = f"""
    <button onClick="changeText({button_id!r}, {message!r}, {timeout_ms!r})"
        class="clipboard-js-btn streamlit-like-btn"
        data-clipboard-text={value!r}
        style={style!r} 
        id={button_id!r}>
        {label}
    </button>    
    """

    widget_js = """
    <script src="https://cdn.jsdelivr.net/npm/clipboard@2.0.10/dist/clipboard.min.js"></script>

    <script>
    new ClipboardJS('.clipboard-js-btn');

    function changeText(buttonId, message, timeout) {
        button = document.getElementById(buttonId);
        let old = button.textContent;
        button.textContent = message;
        setTimeout(() => { 
            button.textContent = old;
         }, timeout);
    }
    </script>
    """

    html(
        widget_css + widget_html + widget_js,
        height=height,
    )
