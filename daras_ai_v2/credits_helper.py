import uuid

import streamlit as st
from furl import furl

from daras_ai_v2 import db
from daras_ai_v2 import settings
from daras_ai_v2.db import get_doc_field


def check_credits(credits_to_deduct: int) -> bool:
    user = st.session_state.get("_current_user")
    if not user:
        return True

    balance = get_doc_field(db.get_user_doc_ref(user.uid), db.USER_BALANCE_FIELD, 0)
    print(">>", user.uid, balance)

    if balance < credits_to_deduct:
        account_url = str(furl(settings.APP_BASE_URL, "/account"))
        if getattr(user, "_is_anonymous", False):
            error = f"Doh! You need to login to run more Gooey.AI recipes. [Login]({account_url}"
        else:
            error = f"Doh! You need to purchase additional credits to run more Gooey.AI recipes. [Buy Credits]({account_url})"
        st.error(error, icon="⚠️")
        return False

    return True


def deduct_credits(amount: int):
    user = st.session_state.get("_current_user")
    if not user:
        return

    db.update_user_balance(user.uid, -abs(amount), f"gooey_in_{uuid.uuid1()}")
