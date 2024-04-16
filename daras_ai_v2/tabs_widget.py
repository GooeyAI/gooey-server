import gooey_ui as st

from daras_ai_v2 import icons
from gooey_ui import option_menu

INTEGRATION_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/c3ba2392-d6b9-11ee-a67b-6ace8d8c9501/image.png"


class MenuTabs:
    run = f"{icons.run} Run"
    examples = f"{icons.example} Examples"
    run_as_api = f"{icons.api} API"
    history = f"{icons.history} History"
    integrations = f'<img align="left" width="24" height="24" style="margin-right: 10px" src="{INTEGRATION_IMG}" alt="Facebook, Whatsapp, Slack, Instagram Icons"> Integrations'
    saved = f"{icons.save} Saved"

    paths = {
        run: "",
        examples: "examples",
        run_as_api: "api",
        history: "history",
        integrations: "integrations",
        saved: "saved",
    }
    paths_reverse = {v: k for k, v in paths.items()}

    display_labels = {
        examples: "Examples",
        history: "History",
        saved: "Saved Runs",
        run_as_api: "API",
        integrations: "Integrations",
    }


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
