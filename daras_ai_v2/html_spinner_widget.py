import gooey_ui as st

from daras_ai_v2.hidden_html_widget import hidden_html_js


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
