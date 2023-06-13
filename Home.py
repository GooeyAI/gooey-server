from gooeysite import wsgi

assert wsgi

import streamlit as st

from daras_ai_v2.settings import GOOEY_AI_PASSWORD


def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == GOOEY_AI_PASSWORD:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password.
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password not correct, show input + error.
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        # Password correct.
        return True


if not check_password():
    st.stop()

"""
## Welcome to Gooey.AI Dashboard

Name|Link
---|---
Main App | [gooey.ai](https://gooey.ai/explore)
Admin | [admin.gooey.ai](https://admin.gooey.ai)
Test App | [gooey-gui.us-1.gooey.ai](https://gooey-gui.us-1.gooey.ai/explore)
Test Admin | [gooey-admin-test.us-1.gooey.ai](http://gooey-admin-test.us-1.gooey.ai)
"""
