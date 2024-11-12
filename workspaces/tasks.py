from django.utils import timezone
from loguru import logger

from app_users.models import AppUser
from celeryapp.celeryconfig import app
from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_app_route_url
from daras_ai_v2.send_email import send_email_via_postmark
from daras_ai_v2.settings import templates


@app.task
def send_invitation_email(invitation_pk: int):
    from workspaces.models import WorkspaceInvite

    invite = WorkspaceInvite.objects.get(pk=invitation_pk)

    assert invite.status == invite.Status.PENDING

    logger.info(
        f"Sending inviation email to {invite.email} for workspace {invite.workspace}..."
    )
    send_email_via_postmark(
        to_address=invite.email,
        from_address=settings.SUPPORT_EMAIL,
        subject=f"[Gooey.AI] Invitation to join {invite.workspace.display_name()}",
        html_body=templates.get_template("workspace_invitation_email.html").render(
            settings=settings,
            invite=invite,
        ),
        message_stream="outbound",
    )

    invite.last_email_sent_at = timezone.now()
    invite.save(update_fields=["last_email_sent_at"])
    logger.info("invite sent. Saved to DB")


@app.task
def send_added_to_workspace_email(workspace_id: int, user_id: int):
    from routers.account import members_route
    from workspaces.models import Workspace

    workspace = Workspace.objects.get(id=workspace_id)
    user = AppUser.objects.get(id=user_id)

    logger.info(
        f"Sending auto-accepted email to {user.email} for workspace {workspace}..."
    )
    send_email_via_postmark(
        to_address=user.email,
        from_address=settings.SUPPORT_EMAIL,
        subject="[Gooey.AI] You've been added to a new Workspace!",
        html_body=templates.get_template("auto_added_to_workspace_email.html").render(
            settings=settings,
            user=user,
            workspace=workspace,
            workspaces_url=get_app_route_url(members_route),
        ),
        message_stream="outbound",
    )
