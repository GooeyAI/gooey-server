from gooeysite import wsgi

assert wsgi
import os

import django
import sentry_sdk
from firebase_admin import auth
from firebase_admin.auth import UserRecord
from furl import furl

import streamlit2 as st
from daras_ai_v2.copy_to_clipboard_button_widget import st_like_btn_css_html
from daras_ai_v2.hidden_html_widget import hidden_html_nojs
from daras_ai_v2.html_spinner_widget import html_spinner_css
from daras_ai_v2.query_params import gooey_get_query_params
from daras_ai_v2.query_params_util import extract_query_params
from daras_ai_v2.st_session_cookie import get_current_user, get_anonymous_user


def init_scripts():
    st.set_page_config(layout="wide")

    # remove fullscreen button and footer
    hidden_html_nojs(st_like_btn_css_html + html_spinner_css)

    if "_current_user" not in st.session_state:
        st.session_state["_current_user"] = get_current_user() or get_anonymous_user()

    current_user = st.session_state.get("_current_user")
    if not current_user:
        st.error("Sorry, we can't let you do that! Please login to continue.")
        st.stop()

    query_params = gooey_get_query_params()
    _, _, uid = extract_query_params(query_params)
    run_user: UserRecord = st.session_state.get("_run_user")
    if uid and (not run_user or run_user.uid != uid):
        if current_user.uid == uid:
            user = current_user
        else:
            user: UserRecord = auth.get_user(uid)
        st.session_state["_run_user"] = user

    with sentry_sdk.configure_scope() as scope:
        scope.set_user(
            {
                "id": current_user.uid,
                "username": current_user.display_name,
                "email": current_user.email,
                "phone_number": current_user.phone_number,
                "photo_url": current_user.photo_url,
            }
        )
        # scope.set_extra("ws_request", get_websocket_request())
        scope.set_extra("query_params", gooey_get_query_params())
        scope.add_event_processor(_event_processor)


def _event_processor(event, hint):
    extra = event.get("extra")
    if extra:
        request_data = {"data": st.session_state.to_dict()}
        base_url = extra.get("base_url")
        if base_url:
            query_params = extra.get("query_params", {})
            request_data["url"] = str(furl(base_url, query_params=query_params))
        ws_request = extra.get("ws_request")
        if ws_request:
            request_data["method"] = ws_request.method
            request_data["headers"] = ws_request.headers
            request_data["env"] = {"REMOTE_ADDR": ws_request.remote_ip}
        event["request"] = request_data
    return event
