import streamlit as st
from daras_ai import db
from daras_ai_v2 import settings


def deduct_credits(credits_to_deduct: int) -> bool:
    user = st.session_state.get("_current_user")
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
    db.deduct_user_credits(uid, credits_to_deduct)
    return True
