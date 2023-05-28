import gooey_ui as st

from daras_ai_v2.hidden_html_widget import hidden_html_js

html_spinner_css = """
<style>
    .gooey-spinner {
      scroll-margin: 20px;
      display: inline-block;
      border: 4px solid rgba(255, 255, 255, 0.2);
      border-top: 4px solid #03dac5;
      border-radius: 50%;
      width: 35px;
      height: 35px;
      animation: spin 1s linear infinite;
    }
    
    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
    
    .gooey-spinner-text {
        padding-left: 8px; 
        padding-top: 2px; 
        vertical-align: top; 
        display: inline-block; 
        font-size: 1.1rem;
    }
</style>
"""


def html_spinner(text: str):
    st.markdown(
        f"""
        <div style="padding-top: 8px; padding-bottom: 8px;">
        <div class="gooey-spinner"></div>
        <div class="gooey-spinner-text">{text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def scroll_to_top():
    hidden_html_js(
        """
<script>
let elem = parent.document.querySelector(`iframe[title="streamlit_option_menu.option_menu"]`);
if (elem) {
    elem.scrollIntoView();
} else {
    top.document.body.scrollTop = 0; // For Safari
    top.document.documentElement.scrollTop = 0; // For Chrome, Firefox, IE and Opera
}
</script>
        """
    )


def scroll_to_spinner():
    hidden_html_js(
        # language=HTML
        """
<script>
setTimeout(() => {
    let elem = document.querySelector('.gooey-spinner');
    if (elem) {
        elem.scrollIntoView();
    }
}, 500);
</script>
        """
    )
