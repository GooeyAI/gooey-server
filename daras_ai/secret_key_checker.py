import streamlit as st
from firebase_admin.auth import UserRecord

from daras_ai_v2 import settings


def is_admin():
    current_user: UserRecord = st.session_state["_current_user"]
    email = current_user.email
    if email and email in settings.ADMIN_EMAILS:
        return True
    return False


def check_secret_key(label, secret_key=settings.APP_SECRET_KEY):
    if secret_key:
        input_text = st.text_input(
            f"Enter secret key to {label}. Contact support@gooey.ai to obtain a secret key.",
        )
        if not input_text:
            return False
        if input_text.strip().lower() != secret_key.lower():
            st.markdown('<p style="color: red">Wrong key!</p>', unsafe_allow_html=True)
            return False
    return True
