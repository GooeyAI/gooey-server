import streamlit as st

from daras_ai_v2 import db
from daras_ai_v2 import settings


def check_credits(credits_to_deduct: int) -> bool:
    user = st.session_state.get("_current_user")
    if not user:
        return True
    uid = user.uid
    if db.get_user_field(uid, "credits") < credits_to_deduct:
        if db.get_user_field(uid, "anonymous_user"):
            st.error(
                f"Doh! You need to login to run more Gooey.AI recipes. [Login]({settings.APP_BASE_URL}/login?next=/) ",
                icon="⚠️",
            )
        else:
            st.error(
                f"Doh! You need to purchase additional credits to run more Gooey.AI recipes. [Buy Credits]({settings.APP_BASE_URL}/account)",
                icon="⚠️",
            )
        return False
    return True


def deduct_credits(credits_to_deduct: int):
    user = st.session_state.get("_current_user")
    if not user:
        return
    db.deduct_user_credits(user.uid, credits_to_deduct)
