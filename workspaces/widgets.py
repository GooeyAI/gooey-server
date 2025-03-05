import gooey_gui as gui
import sentry_sdk
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

from app_users.models import AppUser
from daras_ai_v2 import icons, settings, urls
from daras_ai_v2.fastapi_tricks import get_route_path
from handles.models import COMMON_EMAIL_DOMAINS, Handle
from .models import Workspace, WorkspaceInvite


SESSION_SELECTED_WORKSPACE = "selected-workspace-id"
SWITCH_WORKSPACE_KEY = "--switch-workspace"


def global_workspace_selector(user: AppUser, session: dict):
    from daras_ai_v2.base import BasePage
    from routers.account import members_route, profile_route, saved_route

    try:
        del user.cached_workspaces  # invalidate cache on every re-render
    except AttributeError:
        pass
    workspaces = user.cached_workspaces

    if switch_workspace_id := gui.session_state.pop(SWITCH_WORKSPACE_KEY, None):
        try:
            if str(session[SESSION_SELECTED_WORKSPACE]) == switch_workspace_id:
                raise gui.RedirectException(get_route_path(saved_route))
        except KeyError:
            pass
        set_current_workspace(session, int(switch_workspace_id))

    try:
        current = [
            w for w in workspaces if w.id == session[SESSION_SELECTED_WORKSPACE]
        ][0]
    except (KeyError, IndexError):
        current = workspaces[0]

    popover, content = gui.popover(interactive=True, placement="bottom")

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
                    current.html_icon(),
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
                name=SWITCH_WORKSPACE_KEY,
                type="submit",
                value=str(workspace.id),
                style=dict(height=row_height),
            ):
                with gui.div(className="row align-items-center"):
                    with gui.div(className="col-2 d-flex justify-content-center"):
                        gui.html(workspace.html_icon())
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
                            gui.html(icons.octopus)
                        with gui.div(className="col-10"):
                            gui.html("New Team Workspace")
        else:
            gui.html('<hr class="my-1"/>')
            with gui.link(
                to=get_route_path(saved_route),
                className="text-decoration-none d-block bg-hover-light px-3 my-1 py-1",
                style=dict(height=row_height),
            ):
                with gui.div(className="row align-items-center"):
                    with gui.div(className="col-2 d-flex justify-content-center"):
                        gui.html(icons.octopus)
                    with gui.div(className="col-10"):
                        if current.memberships.get(user=user).can_edit_workspace():
                            gui.html("Manage Workspace")
                        else:
                            gui.html("Open Workspace")

        workspace_creation_dialog = gui.use_alert_dialog(
            key="--create-workspace:dialog"
        )
        if gui.session_state.pop("--create-workspace", None):
            workspace_creation_dialog.set_open(True)

        if workspace_creation_dialog.is_open:
            render_workspace_create_dialog(
                user=user, session=session, ref=workspace_creation_dialog
            )

        gui.html('<hr class="my-1"/>')

        with gui.link(
            to=get_route_path(profile_route),
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
                        str(user.email or user.phone_number),
                        className="d-inline-block text-muted small ms-2",
                        style=dict(marginBottom="0.1rem"),
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


def render_workspace_create_dialog(
    user: AppUser, session: dict, ref: gui.AlertDialogRef
):
    step = gui.session_state.setdefault("workspace:create:step", 1)
    if step == 1:
        title = "#### Create Team Workspace"
        caption = "Workspaces allow you to collaborate with team members with a shared payment method."
        render_fn = lambda: render_workspace_create_step1(
            user=user, session=session, ref=ref
        )
    else:
        if workspace_id := gui.session_state.get("workspace:create:workspace_id"):
            workspace = Workspace.objects.get(id=workspace_id)
        else:
            workspace = get_current_workspace(user, session)

        title = f"#### Invite Members to {workspace.display_name(user)}"
        caption = "This workspace is private and only members can access its workflows and shared billing."
        render_fn = lambda: render_workspace_create_step2(
            user=user, session=session, workspace=workspace, ref=ref
        )

    with gui.alert_dialog(ref=ref, modal_title=title, large=True):
        gui.caption(caption)
        render_fn()


def clear_workspace_create_form():
    keys = [k for k in gui.session_state if k.startswith("workspace:create:")]
    for k in keys:
        gui.session_state.pop(k, None)


def render_workspace_create_step1(
    user: AppUser, session: dict, ref: gui.AlertDialogRef
):
    from daras_ai_v2.profiles import render_handle_input, update_handle

    if "workspace:create:name" not in gui.session_state:
        gui.session_state["workspace:create:name"] = (
            get_default_workspace_name_for_user(user)
        )
    name = gui.text_input(label="###### Name", key=f"workspace:create:name")

    gui.write("###### Your workspace's URL")
    with gui.div(className="d-flex align-items-start gap-2"):
        with gui.div(className="mt-2 pt-1"):
            gui.html(urls.remove_scheme(settings.APP_BASE_URL).rstrip("/") + "/")
        with gui.div(className="flex-grow-1"):
            # separate div for input & error msg for handle field
            if "workspace:create:handle_name" not in gui.session_state:
                gui.session_state["workspace:create:handle_name"] = (
                    Handle.get_suggestion_for_team_workspace(display_name=name)
                )
            handle_name = render_handle_input(
                label="", key="workspace:create:handle_name"
            )

    description = gui.text_input(
        "###### Describe your team",
        key="workspace:create:description",
        placeholder="A plucky team of intrepid folks working to change the world",
    )

    error_msg_container = gui.div()
    with gui.div(className="d-flex justify-content-end align-items-center gap-3"):
        gui.caption("Next: Invite Team Members")

        if gui.button("Cancel", key="workspace:create:cancel", type="secondary"):
            clear_workspace_create_form()
            ref.set_open(False)
            raise gui.RerunException()

        if gui.button(
            "Create Workspace", key="workspace:create:submit", type="primary"
        ):
            workspace = Workspace(name=name, description=description, created_by=user)
            try:
                with transaction.atomic():
                    workspace.handle = update_handle(handle=None, name=handle_name)
                    workspace.create_with_owner()
            except ValidationError as e:
                with error_msg_container:
                    gui.error("\n".join(e.messages))
                return
            except IntegrityError as e:
                with error_msg_container:
                    gui.error(str(e))
                return
            else:
                gui.session_state["workspace:create:step"] = 2
                gui.session_state["workspace:create:workspace_id"] = workspace.id
                raise gui.RerunException()


def render_workspace_create_step2(
    user: AppUser, session: dict, workspace: Workspace, ref: gui.AlertDialogRef
):
    from routers.account import account_route

    max_emails = 5
    emails_csv = gui.text_area(
        label=(
            "###### Emails\n"
            f"Add email addresses for members, separated by commas (up to {max_emails})."
        ),
        placeholder="foo@gooey.ai, bar@gooey.ai, baz@gooey.ai, ...",
        height=5,
        key="workspace:create:emails",
    )

    options = get_workspace_domain_name_options(workspace, user)
    if options:
        workspace.domain_name = gui.selectbox(
            label=(
                "###### Allowed email domain\n"
                "Anyone with this domain will be automatically added as a member to this workspace."
            ),
            format_func=lambda x: x and f"@{x}" or "---",
            options=options,
            key="workspace:create:domain_name",
        )
    else:
        gui.caption("Sign in with your work email to automatically add members.")

    error_msg_container = gui.div()
    with gui.div(className="d-flex justify-content-end gap-2"):
        close_btn = gui.button("Close", key=f"workspace:create:close", type="secondary")
        submit_btn = gui.button("Choose a Plan", type="primary")
        if not close_btn and not submit_btn:
            return

        if submit_btn and emails_csv:
            try:
                emails = validate_emails_csv(emails_csv, max_emails=max_emails)
            except ValidationError as e:
                with error_msg_container:
                    gui.error("\n".join(e.messages))
                return

            for email in emails:
                try:
                    WorkspaceInvite.objects.create_and_send_invite(
                        workspace=workspace,
                        email=email,
                        current_user=user,
                    )
                except (ValidationError, IntegrityError) as e:
                    # log and continue
                    sentry_sdk.capture_exception(e)

        try:
            workspace.full_clean()
            workspace.save(update_fields=["domain_name"])
        except ValidationError as e:
            with error_msg_container:
                gui.error("\n".join(e.messages))
        else:
            set_current_workspace(session, workspace.id)
            if submit_btn:
                raise gui.RedirectException(get_route_path(account_route))
            else:
                clear_workspace_create_form()
                ref.set_open(False)
                raise gui.RerunException()


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


def get_default_workspace_name_for_user(user: AppUser) -> str:
    workspace_count = len(user.cached_workspaces)
    email_domain = user.email and user.email.split("@", maxsplit=1)[1] or ""
    if (
        email_domain
        and email_domain not in COMMON_EMAIL_DOMAINS
        and workspace_count <= 1
    ):
        email_domain_prefix = email_domain.split(".")[0].title()
        return f"{email_domain_prefix} Team"

    suffix = f" {workspace_count - 1}" if workspace_count > 1 else ""
    return f"{user.first_name_possesive()} Team Workspace" + suffix


def get_workspace_domain_name_options(
    workspace: Workspace, current_user: AppUser
) -> set | None:
    current_user_domain = (
        current_user.email and current_user.email.lower().rsplit("@", maxsplit=1)[-1]
    )
    options = {workspace.domain_name, None}
    if current_user_domain not in COMMON_EMAIL_DOMAINS:
        options.add(current_user_domain)
    return len(options) > 1 and options or None


def validate_emails_csv(emails_csv: str, max_emails: int = 5) -> list[str]:
    """Raises ValidationError if an email is invalid"""

    emails = [email.lower().strip() for email in emails_csv.split(",")]
    emails = filter(bool, emails)  # remove empty strings
    emails = set(emails)  # remove duplicates
    emails = list(emails)[:max_emails]  # take up to max_emails from the list

    error_messages = []
    for email in emails:
        try:
            validate_email(email)
        except ValidationError as e:
            error_messages.append(f"{email}: {e.messages[0]}")

    if error_messages:
        raise ValidationError(error_messages)

    return emails
