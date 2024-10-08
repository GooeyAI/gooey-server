from django.utils import timezone
from loguru import logger

from workspaces.models import Workspace
from celeryapp import app
from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_app_route_url
from daras_ai_v2.send_email import send_email_via_postmark
from daras_ai_v2.settings import templates


@app.task
def send_monthly_spending_notification_email(workspace_id: int):
    from routers.account import account_route

    workspace = Workspace.objects.get(id=workspace_id)
    threshold = workspace.subscription.monthly_spending_notification_threshold
    for user in workspace.get_owners():
        if not user.email:
            logger.error(f"Workspace Owner doesn't have an email: {user=}")
            continue

        send_email_via_postmark(
            from_address=settings.SUPPORT_EMAIL,
            to_address=user.email,
            subject=f"[Gooey.AI] Monthly spending has exceeded ${threshold}",
            html_body=templates.get_template(
                "monthly_spending_notification_threshold_email.html"
            ).render(
                user=user,
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


@app.task
def send_payment_failed_email_with_invoice(
    workspace_id: int,
    invoice_url: str,
    dollar_amt: float,
    subject: str,
):
    from routers.account import account_route

    workspace = Workspace.objects.get(id=workspace_id)
    for user in workspace.get_owners():
        if not user.email:
            logger.error(f"User doesn't have an email: {user=}")
            continue

        send_email_via_postmark(
            from_address=settings.PAYMENT_EMAIL,
            to_address=user.email,
            subject=subject,
            html_body=templates.get_template("auto_payment_failed_email.html").render(
                user=user,
                dollar_amt=f"{dollar_amt:.2f}",
                invoice_url=invoice_url,
                account_url=get_app_route_url(account_route),
            ),
            message_stream="billing",
        )


def send_monthly_budget_reached_email(workspace: Workspace):
    from routers.account import account_route

    for user in workspace.get_owners():
        if not user.email:
            continue

        email_body = templates.get_template("monthly_budget_reached_email.html").render(
            user=user,
            workspace=workspace,
            account_url=get_app_route_url(account_route),
        )
        send_email_via_postmark(
            from_address=settings.SUPPORT_EMAIL,
            to_address=user.email,
            subject="[Gooey.AI] Monthly Budget Reached",
            html_body=email_body,
        )

    # IMPORTANT: always use update_fields=... when updating subscription
    # info. We don't want to overwrite other changes made to subscription
    # during the same time
    workspace.subscription.monthly_budget_email_sent_at = timezone.now()
    workspace.subscription.save(update_fields=["monthly_budget_email_sent_at"])
