import streamlit as st

from daras_ai_v2 import settings


def check_secret_key(label, secret_key=settings.SECRET_KEY):
    if secret_key:
        input_text = st.text_input(
            f"Enter secret key to {label}. Contact dev@gooey.ai to obtain a secret key."
        )
        if not input_text:
            return False
        if input_text != secret_key:
            st.markdown('<p style="color: red">Wrong key!</p>', unsafe_allow_html=True)
            return False
    return True
