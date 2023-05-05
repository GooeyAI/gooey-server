import gooey_ui as st


def hidden_html_nojs(raw_html: str):
    st.markdown(
        raw_html.strip(),
        unsafe_allow_html=True,
    )


def hidden_html_js(raw_html: str, is_static=False):
    # if is_static:
    #     raw_html = (
    #         # language=HTML
    #         """
    #         <script>
    #             window.frameElement.parentElement.style.display = "none";
    #         </script>
    #         """
    #         + raw_html
    #     )

    st.html(
        raw_html,
        height=0,
        width=0,
    )
