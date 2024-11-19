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
        subject=f"{invite.created_by.first_name()} invited you to join {invite.workspace.display_name()}",
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
def send_added_to_workspace_email(invite_id: int, user_id: int):
    from routers.account import members_route, saved_route
    from workspaces.models import WorkspaceInvite

    invite = WorkspaceInvite.objects.select_related("workspace", "created_by").get(
        id=invite_id
    )
    user = AppUser.objects.get(id=user_id)

    logger.info(
        f"Sending auto-accepted email to {user.email} for workspace {invite.workspace}..."
    )
    send_email_via_postmark(
        to_address=user.email,
        from_address=settings.SUPPORT_EMAIL,
        subject=f"Welcome to {invite.workspace.display_name()}",
        html_body=templates.get_template("auto_added_to_workspace_email.html").render(
            settings=settings,
            user=user,
            invite=invite,
            workspaces_url=get_app_route_url(members_route),
            saved_url=get_app_route_url(saved_route),
        ),
        message_stream="outbound",
    )
