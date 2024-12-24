import typing

import gooey_gui as gui
from django.contrib.humanize.templatetags.humanize import naturaltime

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

    table_area = gui.div(
        className="table-responsive text-nowrap container-margin-reset"
    )

    if gui.button("＋ Create new API Key"):
        api_key = generate_new_api_key(workspace=workspace, user=user)
        api_keys.insert(0, api_key)

    with table_area:
        with gui.tag("table", className="table table-striped"):
            with gui.tag("thead"), gui.tag("tr"):
                with gui.tag("th"):
                    gui.write("Gooey.AI Key")
                with gui.tag("th"):
                    gui.write("Created At")
                with gui.tag("th"):
                    gui.write("Created By")
                gui.tag("th")
            with gui.tag("tbody"):
                for api_key in api_keys:
                    with gui.tag("tr"):
                        with gui.tag("td"):
                            gui.write(f"`{api_key.preview}`")
                        with gui.tag("td"):
                            gui.write(str(naturaltime(api_key.created_at)))
                        with gui.tag("td"):
                            gui.write(
                                api_key.created_by
                                and api_key.created_by.full_name()
                                or ""
                            )
                        with gui.tag("td"):
                            delete_dialog = gui.use_confirm_dialog(
                                key=f"delete_api_key_{api_key.id}"
                            )
                            gui.button_with_confirm_dialog(
                                ref=delete_dialog,
                                trigger_label=icons.delete,
                                trigger_type="tertiary",
                                trigger_className="text-danger p-0 m-0",
                                modal_title="### Delete API Key",
                                modal_content=f"Are you sure you want to delete `{api_key.preview}`?\n\n"
                                "API requests made using this key will be rejected, "
                                "which could cause any systems still depending on it to break. "
                                "Once deleted, you'll no longer be able to view or modify this API key.",
                                confirm_label="Delete",
                                confirm_className="border-danger bg-danger text-white",
                            )
                            if delete_dialog.pressed_confirm:
                                api_key.delete()
                                gui.rerun()


def generate_new_api_key(workspace: "Workspace", user: AppUser) -> ApiKey:
    api_key, secret_key = ApiKey.objects.create_api_key(workspace, created_by=user)

    gui.success(
        """
**API key generated**
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
