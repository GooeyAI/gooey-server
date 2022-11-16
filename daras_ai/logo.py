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
            <img style="width:150px; height:71px" src="https://storage.googleapis.com/dara-c1b52.appspot.com/gooey/gooey_logo_300x142.png"></img>
        </a>
        <span style="position: absolute; right: 0px">
            <a href="https://dara.network/privacy/">Privacy</a> & 
            <a href="https://dara.network/terms/">Terms</a>
        </span>
        """,
        unsafe_allow_html=True,
    )
    st.write("")
