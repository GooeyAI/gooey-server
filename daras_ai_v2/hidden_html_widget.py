import streamlit as st
import streamlit.components.v1 as components


def hidden_html(raw_html: str):
    el = st.empty()
    with el:
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
