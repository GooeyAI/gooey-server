import typing

import gooey_gui as gui
from absl.flags import ValidationError
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.db import IntegrityError

from daras_ai_v2 import icons
from managed_secrets.models import ManagedSecret

if typing.TYPE_CHECKING:
    from workspaces.models import Workspace
    from bots.models import AppUser


def manage_secrets_view(workspace: "Workspace", user: "AppUser"):
    gui.write(
        "Secrets are protected environment variables that allow you to share Gooey Workflows with private keys that are hidden from viewers of the workflow."
    )

    secrets = list(workspace.managed_secrets.order_by("-created_at"))

    table_area = gui.div(
        className="table-responsive text-nowrap container-margin-reset"
    )

    create_secret_button_with_dialog(
        workspace,
        user,
        button_label=f"{icons.add} Add Secret",
        button_type="secondary",
    )

    with table_area:
        with gui.tag("table", className="table table-striped"):
            with gui.tag("thead"), gui.tag("tr"):
                with gui.tag("th"):
                    gui.write("Name")
                with gui.tag("th"):
                    gui.write("Value")
                with gui.tag("th"):
                    gui.write("Created At")
                with gui.tag("th"):
                    gui.write("Created By")
                gui.tag("th")
            with gui.tag("tbody"):
                for secret in secrets:
                    with gui.tag("tr"):
                        with gui.tag("td"):
                            gui.write(f"`{secret.name}`")
                        with gui.tag("td", className="d-flex gap-3"):
                            if gui.session_state.pop(f"secret:{secret.id}:show", False):
                                secret.load_value()
                            if secret.value:
                                gui.write(f"`{secret.value}`")
                            else:
                                gui.write("`" + "*" * 10 + "`")
                                gui.button(
                                    '<i class="fa-solid fa-eye"></i>',
                                    type="tertiary",
                                    className="m-0 px-1 py-0",
                                    key=f"secret:{secret.id}:show",
                                )
                        with gui.tag("td"):
                            gui.write(str(naturaltime(secret.created_at)))
                        with gui.tag("td"):
                            gui.write(
                                secret.created_by
                                and secret.created_by.full_name()
                                or ""
                            )
                        with gui.tag("td"):
                            edit_secret_button_with_dialog(secret, workspace, user)

                            gui.html('<i class="mx-2 fa-thin fa-pipe"></i>')

                            delete_dialog = gui.use_confirm_dialog(
                                key=f"secrets:{secret.id}:delete"
                            )
                            gui.button_with_confirm_dialog(
                                ref=delete_dialog,
                                trigger_label=icons.delete,
                                trigger_type="tertiary",
                                trigger_className="text-danger p-0 m-0 ",
                                modal_title="### Delete Secret",
                                modal_content=f"Are you sure you want to delete `{secret.name}`?\n\n"
                                "Functions using this secret may throw errors or silently fail, "
                                "which could cause any systems still depending on it to break. "
                                "Once deleted, you'll no longer be able to view or modify this Secret.",
                                confirm_label="Delete",
                                confirm_className="border-danger bg-danger text-white",
                            )
                            if delete_dialog.pressed_confirm:
                                secret.delete()
                                gui.rerun()


def create_secret_button_with_dialog(
    workspace: "Workspace",
    user: "AppUser",
    button_label: str,
    button_type: str,
    button_className: str = "",
) -> ManagedSecret | None:
    dialog = gui.use_confirm_dialog(key="secrets:create", close_on_confirm=False)

    if gui.button(
        label=button_label,
        type=button_type,
        key=dialog.open_btn_key,
        className=button_className,
    ):
        # clear form
        gui.session_state.pop("secret:name", None)
        gui.session_state.pop("secret:value", None)
        dialog.set_open(True)
    if not dialog.is_open:
        return

    with gui.confirm_dialog(
        ref=dialog,
        modal_title="### Add Secret Value",
        confirm_label="Save",
    ):
        gui.caption(
            "The values of protected variables are secret and enable workflow sharing without revealing API keys."
        )
        name = gui.text_input(
            label="###### Name",
            style=dict(textTransform="uppercase", fontFamily="monospace"),
            # language=javascript
            onKeyUp="setValue(value.replace(/ /g, '_').replace(/[^a-zA-Z0-9_\$]/g, ''))",
            key="secret:name",
        ).upper()
        if name and name[0].isdigit():
            gui.error(
                "Secret name must be a valid JS variable name and cannot start with a number."
            )
        value = gui.text_input(
            label="###### Value",
            key="secret:value",
        )

        if workspace.is_personal:
            visible_to = "you"
        else:
            visible_to = "your workspace members"
        gui.caption(
            f"Once entered, secret values are encrypted with your login credentials and only visible to {visible_to}."
        )
        gui.text_input(
            label="###### Workspace",
            value=workspace.display_name(user),
            disabled=True,
        )

        if dialog.pressed_confirm:
            try:
                ManagedSecret.objects.create(
                    workspace=workspace,
                    created_by=user,
                    name=name,
                    value=value,
                )
            except ValidationError as e:
                gui.error(str(e))
                return
            except IntegrityError:
                gui.error(
                    f"Secret with name `{name}` already exists. Please choose a different name."
                )
                return
            dialog.set_open(False)
            gui.rerun()


def edit_secret_button_with_dialog(
    secret: ManagedSecret, workspace: "Workspace", user: "AppUser"
):
    dialog = gui.use_confirm_dialog(
        key=f"secret:{secret.id}:edit", close_on_confirm=False
    )

    if gui.button(
        '<i class="fa-solid fa-pen-to-square"></i>',
        type="link",
        className="p-0 m-0",
        key=dialog.open_btn_key,
    ):
        gui.session_state.pop("secret:name", None)
        gui.session_state.pop("secret:value", None)
        dialog.set_open(True)
    if not dialog.is_open:
        return

    header, body, footer = gui.modal_scaffold()
    with header:
        if secret:
            gui.write(
                f'### Edit <code class="fs-3">{secret.name}</code>',
                unsafe_allow_html=True,
            )
        else:
            gui.write("### Add Secret Value")
    with body:
        gui.caption(
            "The values of protected variables are secret and enable workflow sharing without revealing API keys."
        )

        name = gui.text_input(
            label="###### Name",
            style=dict(textTransform="uppercase", fontFamily="monospace"),
            # language=javascript
            onKeyUp="setValue(value.replace(/ /g, '_').replace(/[^a-zA-Z0-9_\$]/g, ''))",
            key="secret:name",
            value=secret.name,
        )
        if name and name[0].isdigit():
            gui.error(
                "Secret name must be a valid JS variable name and cannot start with a number."
            )
        value = gui.text_input(
            label="###### New Value",
            key="secret:value",
        )

        if workspace.is_personal:
            visible_to = "you"
        else:
            visible_to = "your workspace members"
        gui.caption(
            f"Once entered, secret values are encrypted with your login credentials and only visible to {visible_to}."
        )
        gui.text_input(
            label="###### Workspace",
            value=workspace.display_name(user),
            disabled=True,
        )

    with footer:
        gui.button(
            label="Cancel",
            key=dialog.close_btn_key,
            type="tertiary",
        )
        gui.button(
            label="Save",
            key=dialog.confirm_btn_key,
            type="primary",
        )

    if dialog.pressed_confirm:
        secret.name = name
        secret.value = value
        secret.save()
        dialog.set_open(False)
        gui.rerun()
