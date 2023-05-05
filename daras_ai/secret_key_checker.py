import gooey_ui as st
from firebase_admin.auth import UserRecord

from daras_ai_v2 import settings


def is_admin():
    if "_current_user" not in st.session_state:
        return False
    current_user: UserRecord = st.session_state["_current_user"]
    email = current_user.email
    if settings.DEBUG or (email and email in settings.ADMIN_EMAILS):
        return True
    return False
