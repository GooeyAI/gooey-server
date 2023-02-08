import streamlit as st
import streamlit.components.v1 as components


def hidden_html_nojs(raw_html: str):
    st.markdown(
        raw_html.strip(),
        unsafe_allow_html=True,
    )


def hidden_html_js(raw_html: str):
    components.html(
        """
        <script>
            window.frameElement.parentElement.style.display = "none";
        </script>
        """
        + raw_html,
        height=0,
        width=0,
    )
