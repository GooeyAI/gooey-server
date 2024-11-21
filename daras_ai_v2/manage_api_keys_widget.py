import typing

import gooey_gui as gui
from api_keys.models import ApiKey
from app_users.models import AppUser
from daras_ai_v2 import icons
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_button

if typing.TYPE_CHECKING:
    from workspaces.models import Workspace


def manage_api_keys(workspace: "Workspace", user: AppUser):
    gui.write(
        f"""
{workspace.display_name(current_user=user)} API keys are listed below.
Please note that we do not display your secret API keys again after you generate them.

Do not share your API key with others, or expose it in the browser or other client-side code.

In order to protect the security of your account,
Gooey.AI may also automatically rotate any API key that we've found has leaked publicly.
        """
    )

    api_keys = list(workspace.api_keys.order_by("-created_at"))

    table_area = gui.div()

    if gui.button("＋ Create new secret key"):
        api_key = generate_new_api_key(workspace=workspace, user=user)
        api_keys.insert(0, api_key)

    with table_area:
        import pandas as pd

        gui.table(
            pd.DataFrame.from_records(
                columns=["Secret Key (Preview)", "Created At", "Created By"],
                data=[
                    (
                        api_key.preview,
                        api_key.created_at.strftime("%B %d, %Y at %I:%M:%S %p %Z"),
                        api_key.created_by and api_key.created_by.full_name() or "",
                    )
                    for api_key in api_keys
                ],
            ),
        )


def generate_new_api_key(workspace: "Workspace", user: AppUser) -> ApiKey:
    api_key, secret_key = ApiKey.objects.create_api_key(workspace, created_by=user)

    gui.success(
        """
##### API key generated

Please save this secret key somewhere safe and accessible.
For security reasons, **you won't be able to view it again** through your account.
If you lose this secret key, you'll need to generate a new one.
            """
    )
    col1, col2 = gui.columns([3, 1], responsive=False)
    with col1:
        gui.text_input(
            "recipe url",
            label_visibility="collapsed",
            disabled=True,
            value=secret_key,
        )
    with col2:
        copy_to_clipboard_button(
            f"{icons.link} Copy Secret Key",
            value=secret_key,
            style="height: 3.2rem",
        )

    return api_key
