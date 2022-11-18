import streamlit as st

from daras_ai_v2.hidden_html_widget import hidden_html_js, hidden_html_nojs


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
            let lastHeight = 0;
            const observer = new ResizeObserver(entries => {
                let newHeight = entries[0].contentRect.height;
                if (newHeight == lastHeight) return;
                lastHeight = newHeight;
                top.postMessage({ type: "GOOEY_IFRAME_RESIZE", height: newHeight }, "*");
            });
            observer.observe(parent.document.querySelector('[data-testid="stVerticalBlock"]'));
        </script>
        """
    )
