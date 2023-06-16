from multiprocessing.pool import ThreadPool

from daras_ai_v2.functional import map_parallel
from gooeysite import wsgi
from pages import UsageDashboard

assert wsgi

from django.db import transaction
import streamlit as st
from app_users.models import AppUser
from pages.UsageDashboard import (
    get_all_doc_users,
    get_filtered_auth_users,
)


def main():
    app_users = copy_users_from_firebase()

    st.write("Users to import:", len(app_users))

    if st.button("Commit"):
        with st.spinner("Saving..."):
            with transaction.atomic():
                for user in app_users:
                    try:
                        AppUser.objects.get(uid=user.uid)
                    except AppUser.DoesNotExist:
                        user.save()


@st.cache_resource
def copy_users_from_firebase():
    doc_users = get_all_doc_users()
    auth_users = get_filtered_auth_users(
        user_ids=[doc.id for doc in doc_users],
        exclude_anon=True,
        exclude_disabled=False,
        exclude_team=False,
    )
    return map_parallel(
        lambda user: AppUser(uid=user.uid).copy_from_firebase_user(user),
        list(auth_users.values()),
    )


if __name__ == "__main__":
    with ThreadPool(1000) as pool:
        UsageDashboard.pool = pool
        main()
