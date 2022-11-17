import streamlit as st

from daras_ai import settings


def logo():
    st.set_page_config(layout="wide")

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
        <a href="{settings.DARS_API_ROOT}" target="_top">
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
