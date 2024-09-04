from django.utils import timezone
from loguru import logger

from workspaces.models import Workspace
from celeryapp import app
from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_app_route_url
from daras_ai_v2.send_email import send_email_via_postmark
from daras_ai_v2.settings import templates


@app.task
def send_monthly_spending_notification_email(id: int):
    from routers.account import account_route

    workspace = Workspace.objects.get(id=id)
    threshold = workspace.subscription.monthly_spending_notification_threshold
    for owner in workspace.get_owners():
        if not owner.user.email:
            logger.error(f"Workspace Owner doesn't have an email: {owner=}")
            return

        send_email_via_postmark(
            from_address=settings.SUPPORT_EMAIL,
            to_address=owner.user.email,
            subject=f"[Gooey.AI] Monthly spending has exceeded ${threshold}",
            html_body=templates.get_template(
                "monthly_spending_notification_threshold_email.html"
            ).render(
                user=owner.user,
                workspace=workspace,
                account_url=get_app_route_url(account_route),
            ),
        )

        # IMPORTANT: always use update_fields=... / select_for_update when updating
        # subscription info. We don't want to overwrite other changes made to
        # subscription during the same time
        workspace.subscription.monthly_spending_notification_sent_at = timezone.now()
        workspace.subscription.save(
            update_fields=["monthly_spending_notification_sent_at"]
        )


def send_monthly_budget_reached_email(workspace: Workspace):
    from routers.account import account_route

    for owner in workspace.get_owners():
        if not owner.user.email:
            continue

        email_body = templates.get_template("monthly_budget_reached_email.html").render(
            user=owner.user,
            workspace=workspace,
            account_url=get_app_route_url(account_route),
        )
        send_email_via_postmark(
            from_address=settings.SUPPORT_EMAIL,
            to_address=owner.user.email,
            subject="[Gooey.AI] Monthly Budget Reached",
            html_body=email_body,
        )

    # IMPORTANT: always use update_fields=... when updating subscription
    # info. We don't want to overwrite other changes made to subscription
    # during the same time
    workspace.subscription.monthly_budget_email_sent_at = timezone.now()
    workspace.subscription.save(update_fields=["monthly_budget_email_sent_at"])
