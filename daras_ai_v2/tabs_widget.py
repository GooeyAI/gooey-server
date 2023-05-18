import streamlit2 as st

# from streamlit_option_menu import option_menu
from streamlit2 import option_menu


class MenuTabs:
    run = "🏃‍♀️Run"
    examples = "🔖 Examples"
    run_as_api = "🚀 Run as API"
    history = "📖 History"
    integrations = "🔌 Integrations"


def page_tabs(*, tabs, key=None):
    selected_menu = option_menu(
        None,
        options=tabs,
        icons=["-"] * len(tabs),
        orientation="horizontal",
        key=st.session_state.get(key),
        styles={
            "nav-link": {"white-space": "nowrap;"},
            "nav-link-selected": {"font-weight": "normal;", "color": "black"},
        },
    )
    return selected_menu
