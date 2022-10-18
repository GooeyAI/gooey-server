import streamlit as st


def logo():
    st.markdown(
        """
        <style>
        footer {visibility: hidden;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <a href="/" target="_self">
            <img width=150 src="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/logo.webp"></img>
        </a>
        <a style="position: absolute; right: 0px" href="https://dara.network/privacy/">Privacy Policy</a>
        """,
        unsafe_allow_html=True,
    )
    st.write("")
