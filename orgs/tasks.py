from django.utils import timezone
from loguru import logger

from celeryapp.celeryconfig import app
from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_app_route_url
from daras_ai_v2.send_email import send_email_via_postmark
from daras_ai_v2.settings import templates


@app.task
def send_invitation_email(invitation_pk: int):
    from orgs.models import OrgInvitation

    invitation = OrgInvitation.objects.get(pk=invitation_pk)

    assert invitation.status == invitation.Status.PENDING

    logger.info(
        f"Sending inviation email to {invitation.invitee_email} for org {invitation.org}..."
    )
    send_email_via_postmark(
        to_address=invitation.invitee_email,
        from_address=settings.SUPPORT_EMAIL,
        subject=f"[Gooey.AI] Invitation to join {invitation.org.name}",
        html_body=templates.get_template("org_invitation_email.html").render(
            settings=settings,
            invitation=invitation,
        ),
        message_stream="outbound",
    )

    invitation.last_email_sent_at = timezone.now()
    invitation.save()
    logger.info("Invitation sent. Saved to DB")


@app.task
def send_auto_accepted_email(invitation_pk: int):
    from orgs.models import OrgInvitation
    from routers.account import orgs_route

    invitation = OrgInvitation.objects.get(pk=invitation_pk)
    assert invitation.auto_accepted and invitation.status == invitation.Status.ACCEPTED
    assert invitation.status_changed_by

    user = invitation.status_changed_by
    if not user.email:
        logger.warning(f"User {user} has no email. Skipping auto-accepted email.")
        return

    logger.info(
        f"Sending auto-accepted email to {user.email} for org {invitation.org}..."
    )
    send_email_via_postmark(
        to_address=user.email,
        from_address=settings.SUPPORT_EMAIL,
        subject=f"[Gooey.AI] You've been added to a new team!",
        html_body=templates.get_template(
            "org_invitation_auto_accepted_email.html"
        ).render(
            settings=settings,
            user=user,
            org=invitation.org,
            orgs_url=get_app_route_url(orgs_route),
        ),
        message_stream="outbound",
    )
