import streamlit as st

from daras_ai import settings


def check_secret_key(label):
    if settings.SECRET_KEY:
        secret_key = st.text_input(
            f"Enter secret key to {label}. Contact dev@dara.network to obtain a secret key."
        )
        if secret_key != settings.SECRET_KEY:
            return False
    return True
