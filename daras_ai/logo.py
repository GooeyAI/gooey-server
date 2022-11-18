import streamlit as st

from daras_ai_v2.hidden_html_widget import hidden_html


def logo():
    st.set_page_config(layout="wide")

    hidden_html(
        """
        <style>
        footer {
            visibility: hidden;
        }
        </style>

        <script>
            function fit() {
                top.postMessage({
                    "type": "GOOEY_IFRAME_RESIZE",
                    "height": parent.document.getElementsByClassName("main")[0].scrollHeight,
                }, "*");
            }
            setInterval(fit, 50);
        </script>
        """
    )
