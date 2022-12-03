import streamlit as st
from daras_ai import db
from daras_ai_v2 import settings

slug_credits_pair = {}


# If we want to deduct credits for a particular reciepe other than default credits value, then add a recipe slug to
# slug_credits_pair with key as slug and credits number as value. Ex: {'FaceInpainting': 10}

def get_credits_to_deduct_from_slug(slug: str):
    try:
        return int(slug_credits_pair[slug])

    except:
        return int(settings.CREDITS_TO_DEDUCT_PER_RUN)


def deduct_credits(slug: str) -> bool:
    credits_to_deduct = get_credits_to_deduct_from_slug(slug)
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
