import datetime

import pandas as pd
import streamlit as st
from firebase_admin import auth

from daras_ai_v2 import db
from daras_ai_v2.copy_to_clipboard_button_widget import (
    copy_to_clipboard_button,
)
from daras_ai_v2.crypto import (
    get_random_string,
    PBKDF2PasswordHasher,
    safe_preview,
    RANDOM_STRING_CHARS,
)
from daras_ai_v2.hidden_html_widget import hidden_html_nojs


def manage_api_keys(user: auth.UserRecord):
    st.write(
        """
Your secret API keys are listed below. 
Please note that we do not display your secret API keys again after you generate them.

Do not share your API key with others, or expose it in the browser or other client-side code. 

In order to protect the security of your account, 
Gooey.AI may also automatically rotate any API key that we've found has leaked publicly.
        """
    )

    db_collection = db._db.collection(db.API_KEYS_COLLECTION)
    api_keys = _load_api_keys(db_collection, user)

    table_area = st.container()

    if st.button("＋ Create new secret key"):
        with st.spinner("Generating a new API key..."):
            doc = _generate_new_key_doc()
            doc["uid"] = user.uid
            api_keys.append(doc)
            db_collection.add(doc)

    with table_area:
        st.table(
            pd.DataFrame.from_records(
                columns=["Secret Key (Preview)", "Created At"],
                data=[
                    (api_key["secret_key_preview"], api_key["created_at"])
                    for api_key in api_keys
                ],
            ),
        )
        # hide table index
        hidden_html_nojs(
            """
            <style>
            table {font-family:"Source Code Pro", monospace}
            thead tr th:first-child {display:none}
            tbody th {display:none}
            </style>
            """
        )


def _load_api_keys(db_collection, user):
    api_keys = st.session_state.setdefault("__api_keys", [])
    if not api_keys:
        with st.spinner("Loading API Keys..."):
            api_keys.extend(
                [
                    snap.to_dict()
                    for snap in db_collection.where("uid", "==", user.uid)
                    # .order_by("created_at")
                    .get()
                ]
            )
    return api_keys


def _generate_new_key_doc() -> dict:
    new_api_key = "gsk-" + get_random_string(
        length=48, allowed_chars=RANDOM_STRING_CHARS
    )

    hasher = PBKDF2PasswordHasher()
    secret_key_hash = hasher.encode(new_api_key, hasher.salt())
    created_at = datetime.datetime.utcnow()

    st.success(
        f"""
##### API key generated

Please save this secret key somewhere safe and accessible. 
For security reasons, **you won't be able to view it again** through your account. 
If you lose this secret key, you'll need to generate a new one.
            """
    )
    col1, col2 = st.columns([3, 1])
    with col1:
        st.text_input(
            "recipe url",
            label_visibility="collapsed",
            disabled=True,
            value=new_api_key,
        )
    with col2:
        copy_to_clipboard_button(
            "📎 Copy Secret Key",
            value=new_api_key,
            style="padding: 6px",
            height=55,
        )

    return {
        "secret_key_hash": secret_key_hash,
        "secret_key_preview": safe_preview(new_api_key),
        "created_at": created_at,
    }
