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


def manage_secrets_table(workspace: "Workspace", user: "AppUser"):
    gui.write(
        "Secrets are protected environment variables that allow you to share Gooey Workflows with private keys that are hidden from viewers of the workflow."
    )

    secrets = list(workspace.managed_secrets.order_by("-created_at"))

    table_area = gui.div(
        className="table-responsive text-nowrap container-margin-reset"
    )

    edit_secret_button_with_dialog(
        workspace,
        user,
        trigger_label=f"{icons.add} Add Secret",
        trigger_type="secondary",
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
                            edit_secret_button_with_dialog(
                                workspace,
                                user,
                                secret=secret,
                                trigger_label='<i class="fa-solid fa-pen-to-square"></i>',
                                trigger_type="link",
                                trigger_className="p-0 m-0",
                            )

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


def edit_secret_button_with_dialog(
    workspace: "Workspace",
    user: "AppUser",
    *,
    trigger_label: str,
    trigger_type: str,
    trigger_className: str = "",
    secret: ManagedSecret | None = None,
):
    if secret:
        key = f"secret:{secret.id}:edit"
    else:
        key = "secret:create"
    dialog = gui.use_confirm_dialog(key=key, close_on_confirm=False)

    if gui.button(
        label=trigger_label,
        type=trigger_type,
        key=dialog.open_btn_key,
        className=trigger_className,
    ):
        gui.session_state.pop("secret:name", None)
        gui.session_state.pop("secret:value", None)
        dialog.set_open(True)
    if not dialog.is_open:
        return

    header, body, footer = gui.modal_scaffold()

    with header:
        if secret:
            title = f'### Edit <code class="fs-3">{secret.name}</code>'
        else:
            title = "### Add Secret Value"
        gui.write(title, unsafe_allow_html=True)

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
            value=secret and secret.name,
        )
        if name and name[0].isdigit():
            gui.error(
                "Secret name must be a valid JS variable name and cannot start with a number."
            )
            name = None
        if secret:
            value_label = "###### New Value"
        else:
            value_label = "###### Value"
        value = gui.text_input(label=value_label, key="secret:value")

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
        gui.div(className="mb-4")

    with footer:
        gui.button(
            label="Cancel",
            key=dialog.close_btn_key,
            type="tertiary",
        )
        gui.button(
            label=f"{icons.save} Save",
            key=dialog.confirm_btn_key,
            type="primary",
            disabled=not (name and value),
        )

    if not dialog.pressed_confirm:
        return
    try:
        if secret:
            secret.name = name
            secret.value = value
            secret.full_clean()
            secret.save()
            dialog.set_open(False)
        else:
            ManagedSecret.objects.create(
                workspace=workspace,
                created_by=user,
                name=name,
                value=value,
            )
    except ValidationError as e:
        gui.error(e.messages[0], icon="")
    except IntegrityError:
        gui.error(
            f"Secret with name `{name}` already exists. Please choose a different name."
        )
    else:
        dialog.set_open(False)
        raise gui.RedirectException
