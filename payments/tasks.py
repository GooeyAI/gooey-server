from datetime import datetime, timezone

from furl import furl
from loguru import logger

from app_users.models import AppUser
from celeryapp import app
from daras_ai_v2 import settings
from daras_ai_v2.send_email import send_email_via_postmark
from daras_ai_v2.settings import templates


ACCOUNT_URL = str(furl(settings.APP_BASE_URL) / "account" / "")


@app.task
def send_email_budget_reached(user_id: int):
    user = AppUser.objects.get(id=user_id)
    if not user.email:
        return

    email_body = templates.get_template("monthly_budget_reached_email.html").render(
        user=user,
        account_url=ACCOUNT_URL,
    )
    send_email_via_postmark(
        from_address=settings.SUPPORT_EMAIL,
        to_address=user.email,
        subject="[Gooey.AI] Monthly Budget Reached",
        html_body=email_body,
    )

    user.subscription.monthly_budget_email_sent_at = datetime.now(timezone.utc)
    user.subscription.save()


@app.task
def send_email_auto_recharge_failed(user_id: int):
    user = AppUser.objects.get(id=user_id)
    if not user.email:
        return

    email_body = templates.get_template("auto_recharge_failed_email.html").render(
        user=user,
        account_url=ACCOUNT_URL,
    )
    send_email_via_postmark(
        from_address=settings.SUPPORT_EMAIL,
        to_address=user.email,
        subject="[Gooey.AI] Auto-Recharge failed",
        html_body=email_body,
    )


@app.task
def send_monthly_spending_notification_email(user_id: int):
    user = AppUser.objects.get(id=user_id)
    if not user.email:
        logger.error(f"User doesn't have an email: {user=}")
        return

    threshold = user.subscription.monthly_spending_notification_threshold

    send_email_via_postmark(
        from_address=settings.SUPPORT_EMAIL,
        to_address=user.email,
        subject=f"[Gooey.AI] Monthly spending has exceeded ${threshold}",
        html_body=templates.get_template(
            "monthly_spending_notification_threshold_email.html"
        ).render(
            user=user,
            account_url=ACCOUNT_URL,
        ),
    )

    user.subscription.monthly_spending_notification_sent_at = datetime.now(
        tz=timezone.utc
    )
    user.subscription.save(update_fields=["monthly_spending_notification_sent_at"])
