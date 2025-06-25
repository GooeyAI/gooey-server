from __future__ import annotations

import typing

import gooey_gui as gui
import sentry_sdk
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from fastapi.exceptions import HTTPException
from fastapi.requests import Request
from fastapi.responses import RedirectResponse
from furl import furl

from app_users.models import AppUser
from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_route_path
from daras_ai_v2.meta_content import raw_build_meta_tags
from handles.models import Handle, COMMON_EMAIL_DOMAINS
from routers.custom_api_router import CustomAPIRouter
from workspaces.models import Workspace, WorkspaceInvite, WorkspaceRole
from workspaces.widgets import (
    get_current_workspace,
    set_current_workspace,
    get_workspace_domain_name_options,
)
import re

if typing.TYPE_CHECKING:
    pass

app = CustomAPIRouter()


@gui.route(app, "/workspaces/create/")
def create_workspace_route(
    request: Request, selected_plan: int | None = None, next: str | None = None
):
    """Render the workspace creation popup step 1."""
    if not request.user or request.user.is_anonymous:
        redirect_url = furl("/login", query_params={"next": request.url})
        return RedirectResponse(str(redirect_url))

    with gui.div(className="container mt-5"):
        render_create_workspace_form(
            user=request.user,
            session=request.session,
            selected_plan=selected_plan,
            next_url=next,
        )

    return {
        "meta": raw_build_meta_tags(
            url=request.url.path,
            title="Create Workspace",
            description="Create a new workspace on Gooey.AI",
        ),
    }


@gui.route(app, "/workspaces/create/invite-team/")
def workspace_invite_team_route(
    request: Request, selected_plan: int | None = None, next: str | None = None
):
    if not request.user or request.user.is_anonymous:
        redirect_url = furl("/login", query_params={"next": request.url})
        return RedirectResponse(str(redirect_url))

    workspace = get_current_workspace(request.user, request.session)

    # Check if user has permission to invite members
    if not workspace.get_admins().filter(id=request.user.id).exists():
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to invite members to this workspace",
        )

    with gui.div(className="container mt-5"):
        render_invite_team_form(
            workspace=workspace,
            user=request.user,
            selected_plan=selected_plan,
            next_url=next,
        )

    return {
        "meta": raw_build_meta_tags(
            url=request.url.path,
            title="Invite Team Members",
            description="Invite team members to your new workspace",
        ),
    }


def render_create_workspace_form(
    user: AppUser, session: dict, selected_plan: int | None, next_url: str
):
    from daras_ai_v2.profiles import render_handle_input, update_handle

    gui.write("#### Create Gooey.AI Workspace")
    gui.caption(
        "Workspaces allow you to collaborate with team members with a shared payment method."
    )

    if "workspace_name" not in gui.session_state:
        gui.session_state["workspace_name"] = get_default_workspace_name_for_user(user)
    name = gui.text_input(label="###### Name", key="workspace_name")

    gui.write("###### Your workspace's URL")
    with gui.div(className="d-flex align-items-start gap-2"):
        with gui.div(className="mt-2 pt-1"):
            # rstrip("/") + "/" to preserve exactly one trailing slash
            gui.html(settings.APP_BASE_URL.rstrip("/") + "/")
        with gui.div(className="d-block d-lg-flex gap-3 w-100"):
            # separate div for input & error msg for handle field
            if "handle_name" not in gui.session_state:
                gui.session_state["handle_name"] = (
                    Handle.get_suggestion_for_team_workspace(display_name=name)
                )
            handle_name = render_handle_input(label="", key="handle_name")

    description = gui.text_input(
        "###### Describe your team",
        key="workspace:create:description",
        placeholder="A plucky team of intrepid folks working to change the world",
    )

    error_msg_container = gui.div()

    with gui.div(className="d-flex justify-content-end align-items-center gap-3"):
        gui.caption("Next: Invite Team Members")

        gui.button("Cancel", onClick=popup_close_or_navgiate_js(next_url))

        if not gui.button("Create Workspace", type="primary"):
            return

    workspace = Workspace(name=name, description=description, created_by=user)
    try:
        with transaction.atomic():
            workspace.handle = update_handle(handle=None, name=handle_name)
            workspace.create_with_owner()
    except ValidationError as e:
        with error_msg_container:
            gui.error("\n".join(e.messages))
    except IntegrityError as e:
        with error_msg_container:
            gui.error(str(e))
    else:
        set_current_workspace(session, workspace.id)
        next_url = furl(
            get_route_path(workspace_invite_team_route), query_params={"next": next_url}
        )
        if selected_plan:
            next_url.query.params["selected_plan"] = selected_plan
        gui.js(
            # language=javascript
            """
            window.opener?.postMessage({ workspaceCreated: true }, "*");
            gui.navigate(nextUrl);
            """,
            nextUrl=str(next_url),
        )


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


def render_invite_team_form(
    workspace: Workspace, user: AppUser, selected_plan: int | None, next_url: str
):
    gui.write(f"### Invite members to {workspace.display_name()} on Gooey.AI")
    gui.caption(
        "This workspace is private and only members can access its workflows and shared billing."
    )
    max_emails = 5
    emails_csv = render_emails_csv_input(max_emails=5, key="workspace:create:emails")

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

    error_msg_container = gui.div()
    with gui.div(className="d-flex justify-content-end gap-2 mt-2"):
        close_btn = gui.button("Close")

        if selected_plan:
            label = "Add Payment Method"
        else:
            label = "Choose a Plan"
        submit_btn = gui.button(label, type="primary")
        if not (submit_btn or close_btn):
            return

    validate_and_invite_from_emails_csv(
        emails_csv,
        workspace=workspace,
        current_user=user,
        error_msg_container=error_msg_container,
        max_emails=max_emails,
    )

    try:
        workspace.full_clean()
        workspace.save(update_fields=["domain_name"])
    except ValidationError as e:
        with error_msg_container:
            gui.error("\n".join(e.messages))
    else:
        gui.js(popup_close_or_navgiate_js(next_url))


def render_emails_csv_input(max_emails: int, key: str) -> str:
    return gui.text_area(
        label=(
            "###### Emails\n"
            f"Add email addresses for members, separated by commas (up to {max_emails})."
        ),
        placeholder="foo@gooey.ai, bar@gooey.ai, baz@gooey.ai, ...",
        height=5,
        key=key,
    )


def validate_and_invite_from_emails_csv(
    emails_csv: str,
    workspace: Workspace,
    current_user: AppUser,
    error_msg_container: gui.NestingCtx,
    role: WorkspaceRole = WorkspaceRole.MEMBER,
    max_emails: int = 5,
):
    if not emails_csv:
        return

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
                current_user=current_user,
                defaults=dict(role=role),
            )
        except (ValidationError, IntegrityError) as e:
            # log and continue
            sentry_sdk.capture_exception(e)
    return True


def popup_close_or_navgiate_js(next_url: str) -> str:
    return (
        # language=javascript
        """
        if (event) event.preventDefault();
        if (window.opener) { 
            window.close();
        } else {
            gui.navigate(%r);
        }
        """
        % next_url
    )


delimiters = re.compile(r"[\s,;|]+")


def validate_emails_csv(emails_csv: str, max_emails: int = 5) -> list[str]:
    """Raises ValidationError if an email is invalid"""

    emails = [email.lower().strip() for email in delimiters.split(emails_csv)]
    emails = filter(bool, emails)  # remove empty strings
    emails = set(emails)  # remove duplicates
    emails = list(emails)[:max_emails]  # take up to max_emails from the list

    error_messages = []
    for email in emails:
        try:
            validate_email(email)
        except ValidationError as e:
            error_messages.append(f'"{email}": {e.messages[0]}')

    if error_messages:
        raise ValidationError(error_messages)

    return emails
