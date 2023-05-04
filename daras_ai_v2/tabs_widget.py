import streamlit2 as st

# from streamlit_option_menu import option_menu
from streamlit2 import option_menu


class MenuTabs:
    run = "🏃‍♀️Run"
    examples = "🔖 Examples"
    run_as_api = "🚀 Run as API"
    history = "📖 History"
    integrations = "🔌 Integrations"

    paths = {
        run: "",
        examples: "examples",
        run_as_api: "api",
        history: "history",
        integrations: "integrations",
    }
    paths_reverse = {v: k for k, v in paths.items()}


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
