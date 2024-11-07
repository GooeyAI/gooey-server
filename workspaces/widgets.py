import gooey_gui as gui
from django.core.exceptions import ValidationError

from app_users.models import AppUser
from daras_ai_v2 import icons, settings
from daras_ai_v2.fastapi_tricks import get_route_path
from handles.models import COMMON_EMAIL_DOMAINS
from .models import Workspace, WorkspaceInvite, WorkspaceRole


SESSION_SELECTED_WORKSPACE = "selected-workspace-id"


def workspace_selector(user: AppUser, session: dict, *, key: str = "global-selector"):
    from daras_ai_v2.base import BasePage
    from routers.account import members_route

    workspaces = user.get_workspaces().order_by("-is_personal", "-created_at")
    if not workspaces:
        workspaces = [user.get_or_create_personal_workspace()[0]]

    if str(gui.session_state.get(key)).startswith("__url:"):
        raise gui.RedirectException(gui.session_state[key].removeprefix("__url:"))

    if switch_workspace_id := gui.session_state.pop("--switch-workspace", None):
        set_current_workspace(session, int(switch_workspace_id))

    try:
        current = [
            w for w in workspaces if w.id == session[SESSION_SELECTED_WORKSPACE]
        ][0]
    except (KeyError, IndexError):
        current = workspaces[0]

    popover, content = gui.popover(interactive=True)

    with popover:
        if current.is_personal and current.created_by_id == user.id:
            if len(workspaces) == 1:
                display_name = user.first_name()
            else:
                display_name = "Personal"
        else:
            display_name = current.display_name(user)
        gui.html(
            " ".join(
                [
                    current.html_icon(user),
                    display_name,
                    '<i class="ps-1 fa-regular fa-chevron-down"></i>',
                ],
            ),
        )

    with content, gui.div(
        className="d-flex flex-column bg-white border border-dark rounded shadow mx-2 overflow-hidden",
    ):
        row_height = "2.2rem"

        for workspace in workspaces:
            with gui.tag(
                "button",
                className="bg-transparent border-0 text-start bg-hover-light px-3 my-1",
                name="--switch-workspace",
                type="submit",
                value=str(workspace.id),
                style=dict(height=row_height),
            ):
                with gui.div(className="row align-items-center"):
                    with gui.div(className="col-2 d-flex justify-content-center"):
                        gui.html(workspace.html_icon(user))
                    with gui.div(
                        className="col-10 d-flex justify-content-between align-items-center"
                    ):
                        with gui.div(className="pe-3"):
                            gui.html(workspace.display_name(user))
                        if workspace.id == current.id:
                            gui.html(
                                '<i class="fa-sharp fa-solid fa-circle-check"></i>'
                            )

        if current.is_personal:
            if BasePage.is_user_admin(user):
                gui.html('<hr class="my-1"/>')
                with gui.tag(
                    "button",
                    className="bg-transparent border-0 text-start bg-hover-light px-3 my-1",
                    name="--create-workspace",
                    type="submit",
                    value="yes",
                    style=dict(height=row_height),
                ):
                    with gui.div(className="row align-items-center"):
                        with gui.div(className="col-2 d-flex justify-content-center"):
                            gui.html('<i class="fa-regular fa-octopus"></i>')
                        with gui.div(className="col-10"):
                            gui.html("New Team Workspace")
        else:
            gui.html('<hr class="my-1"/>')
            with gui.link(
                to=get_route_path(members_route),
                className="text-decoration-none d-block bg-hover-light px-3 my-1 py-1",
                style=dict(height=row_height),
            ):
                with gui.div(className="row align-items-center"):
                    with gui.div(className="col-2 d-flex justify-content-center"):
                        gui.html('<i class="fa-regular fa-octopus"></i>')
                    with gui.div(className="col-10"):
                        gui.html("Manage Workspace")

        if gui.session_state.pop("--create-workspace", None):
            name = f"{user.first_name_possesive()} Team Workspace"
            if len(workspaces) > 1:
                name += f" {len(workspaces) - 1}"
            workspace = Workspace(name=name, created_by=user)
            workspace.create_with_owner()
            gui.session_state[key] = workspace.id
            session[SESSION_SELECTED_WORKSPACE] = workspace.id
            raise gui.RedirectException(get_route_path(members_route))

        gui.html('<hr class="my-1"/>')

        with gui.link(
            to="/account/profile/",
            className="text-decoration-none d-block bg-hover-light align-items-center px-3 my-1 py-1",
            style=dict(height=row_height),
        ):
            with gui.div(className="row align-items-center"):
                with gui.div(className="col-2 d-flex justify-content-center"):
                    gui.html(icons.profile)
                with gui.div(
                    className="col-10 d-flex justify-content-between align-items-end"
                ):
                    gui.html(
                        "Profile",
                        className="d-inline-block",
                    )
                    gui.html(
                        user.email or user.phone_number,
                        className="d-inline-block text-muted small",
                    )

        with gui.div(className="d-lg-none d-inline-block"):
            for url, label in settings.HEADER_LINKS:
                with gui.tag(
                    "a",
                    href=url,
                    className="text-decoration-none d-block bg-hover-light align-items-center px-3 my-1 py-1",
                    style=dict(height=row_height),
                ):
                    col1, col2 = gui.columns([2, 10], responsive=False)
                    with col2:
                        gui.html(label)

        with gui.tag(
            "a",
            href="/logout/",
            className="text-decoration-none d-block bg-hover-light align-items-center px-3 my-1 py-1",
            style=dict(height=row_height),
        ):
            with gui.div(className="row align-items-center"):
                with gui.div(className="col-2 d-flex justify-content-center"):
                    gui.html(icons.sign_out)
                with gui.div(className="col-10"):
                    gui.html("Log out")

    return current


def get_current_workspace(user: AppUser, session: dict) -> Workspace:
    try:
        workspace_id = session[SESSION_SELECTED_WORKSPACE]
        return Workspace.objects.get(
            id=workspace_id,
            memberships__user=user,
            memberships__deleted__isnull=True,
        )
    except (KeyError, Workspace.DoesNotExist):
        workspace = user.get_or_create_personal_workspace()[0]
        set_current_workspace(session, workspace.id)
        return workspace


def set_current_workspace(session: dict, workspace_id: int):
    session[SESSION_SELECTED_WORKSPACE] = workspace_id


def create_workspace_with_defaults(user: AppUser, name: str | None = None):
    if not name:
        workspace_count = user.get_workspaces().count()
        suffix = f" {workspace_count - 1}" if workspace_count > 1 else ""
        name = get_default_name_for_new_workspace(user, suffix=suffix)
    workspace = Workspace(name=name, created_by=user)
    workspace.create_with_owner()
    return workspace


def get_default_name_for_new_workspace(user: AppUser, suffix: str = "") -> str:
    email_domain = user.email and user.email.split("@", maxsplit=1)[1] or ""
    if (
        email_domain
        and email_domain not in COMMON_EMAIL_DOMAINS
        and user.get_workspaces().count() <= 1
    ):
        email_domain_prefix = email_domain.split(".")[0].title()
        return f"{email_domain_prefix} Team"

    return f"{user.first_name_possesive()} Team Workspace" + suffix


def render_workspace_creation_dialog(
    ref: gui.ConfirmDialogRef,
    *,
    user: AppUser,
    session: dict,
) -> Workspace | None:
    step_2_ref = gui.use_confirm_dialog(
        key="--create-workspace-step-2", close_on_confirm=False
    )

    if ref.is_open:
        _render_workspace_creation_dialog_step_1(ref, user=user, session=session)
    if step_2_ref.is_open:
        _render_workspace_creation_dialog_step_2(step_2_ref, user=user, session=session)

    if ref.pressed_confirm:
        step_2_ref.set_open(True)
        raise gui.RerunException()
    if step_2_ref.pressed_confirm:
        ref.set_open(False)
        return get_current_workspace(user, session)


def _render_workspace_creation_dialog_step_1(
    ref: gui.ConfirmDialogRef, *, user: AppUser, session: dict
):
    from routers.account import account_route

    with gui.confirm_dialog(
        ref=ref,
        modal_title="#### Create Team Workspace",
        confirm_label="Create Workspace",
    ):
        gui.caption(
            "Workspaces allow you to collaborate with team members with a shared payment method."
        )

        workspace_name = gui.text_input(
            "##### Name",
            value=get_default_name_for_new_workspace(user),
        )
        gui.write("##### Billing")
        gui.caption(
            "Your first workspace gets 500 ($5) Credits. Add a payment method for shared billing."
        )
        add_payment_method_button = gui.button("Add Payment Method", type="link")

        if not ref.pressed_confirm and not add_payment_method_button:
            return

        workspace = create_workspace_with_defaults(user, name=workspace_name)
        set_current_workspace(session, workspace.id)

        if add_payment_method_button:
            raise gui.RedirectException(get_route_path(account_route))


def _render_workspace_creation_dialog_step_2(
    ref: gui.ConfirmDialogRef, *, user: AppUser, session: dict
):
    workspace = get_current_workspace(user, session)
    with gui.confirm_dialog(
        ref=ref,
        modal_title=f"#### Invite members to {workspace.display_name()}",
        confirm_label="Done",
        cancel_className="d-none",  # hack
    ):
        gui.write("##### Invite Members")
        with gui.div(className="d-flex"):
            with gui.div(className="flex-grow-1"):
                email = gui.text_input("")
            pressed_invite = gui.button(f"{icons.send} Invite", type="tertiary")

        if pressed_invite:
            try:
                WorkspaceInvite.objects.create_and_send_invite(
                    workspace=workspace,
                    email=email,
                    user=user,
                    defaults=dict(role=WorkspaceRole.ADMIN),
                )
            except ValidationError as e:
                gui.error("\n".join(e.messages))
            else:
                gui.success("Invitation sent!")

        email_domain = user.email and user.email.split("@")[-1]
        if email_domain and email_domain.lower() not in COMMON_EMAIL_DOMAINS:
            gui.write("##### Email Domain")
            gui.caption(
                "Anyone with this email domain will be automatically added as member to this workspace"
            )
            workspace.domain_name = gui.selectbox(
                label="",
                options=[email_domain],
                format_func=lambda s: s and f"@{s}" or "&mdash;" * 3,
                value=email_domain,
                allow_none=True,
            )

    if ref.pressed_confirm:
        if workspace.domain_name:
            workspace.save(update_fields=["domain_name"])
        ref.set_open(False)
