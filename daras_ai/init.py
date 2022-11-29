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
            const stBlock = parent.document.querySelector('[data-testid="stVerticalBlock"]');

            const observer = new ResizeObserver(entries => {
                notifyHeight(entries[0].contentRect.height);
            });
            observer.observe(stBlock);

            setInterval(function() {
                notifyHeight(stBlock.clientHeight)
            }, 500);
            
            let lastHeight = 0;
        
            function notifyHeight(height) {
                if (lastHeight == height) return;
                lastHeight = height;
                top.postMessage({ type: "GOOEY_IFRAME_RESIZE", height: height }, "*");
            }
        </script>
        """
    )
    if "_current_user" not in st.session_state:
        st.session_state["_current_user"] = get_current_user() or get_anonymous_user()
