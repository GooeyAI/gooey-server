import streamlit as st

from daras_ai_v2.hidden_html_widget import hidden_html_js, hidden_html_nojs
from daras_ai_v2.st_session_cookie import get_current_user, get_anonymous_user


def init_scripts():
    st.set_page_config(layout="wide")

    # remove fullscreen button and footer
    hidden_html_nojs(
        """
        <style>
        button[title="View fullscreen"], footer {
            visibility: hidden;
        }
        </style>
        """
    )

    # for automatically resizing the iframe
    hidden_html_js(
        """
        <script>
            const observer = new ResizeObserver(entries => {
                let height = entries[0].contentRect.height;
                top.postMessage({ type: "GOOEY_IFRAME_RESIZE", height: height }, "*");
            });
            observer.observe(parent.document.querySelector('[data-testid="stVerticalBlock"]'));
        </script>
        """
    )

    if "_current_user" not in st.session_state:
        st.session_state["_current_user"] = get_current_user() or get_anonymous_user()
