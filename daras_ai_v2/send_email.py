import sys
import typing

import requests
from loguru import logger

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.fastapi_tricks import get_app_route_url
from daras_ai_v2.settings import templates


if typing.TYPE_CHECKING:
    from app_users.models import AppUser
    from workspaces.models import Workspace


def send_reported_run_email(
    *,
    user: "AppUser",
    run_uid: str,
    url: str,
    recipe_name: str,
    report_type: str,
    reason_for_report: str,
    error_msg: str,
):
    recipeints = "support@gooey.ai, devs@gooey.ai"
    html_body = templates.get_template("report_email.html").render(
        user=user,
        run_uid=run_uid,
        url=url,
        recipe_name=recipe_name,
        report_type=report_type,
        reason_for_report=reason_for_report,
        error_msg=error_msg,
    )
    send_email_via_postmark(
        from_address=settings.SUPPORT_EMAIL,
        to_address=user.email or recipeints,
        bcc=recipeints,
        subject=f"Thanks for reporting {recipe_name} on Gooey.AI",
        html_body=html_body,
    )


def send_low_balance_email(
    *,
    workspace: "Workspace",
    total_credits_consumed: int,
):
    from routers.account import account_route

    logger.info("Sending low balance email...")

    recipeints = "support@gooey.ai, devs@gooey.ai"
    for user in workspace.get_owners():
        html_body = templates.get_template("low_balance_email.html").render(
            user=user,
            workspace=workspace,
            url=get_app_route_url(account_route),
            total_credits_consumed=total_credits_consumed,
            settings=settings,
        )
        send_email_via_postmark(
            from_address=settings.SUPPORT_EMAIL,
            to_address=user.email or recipeints,
            bcc=recipeints,
            subject="Your Gooey.AI credit balance is low",
            html_body=html_body,
        )


is_running_pytest = "pytest" in sys.modules
pytest_outbox = []


def send_email_via_postmark(
    *,
    from_address: str,
    to_address: str,
    cc: str | None = None,
    bcc: str | None = None,
    subject: str = "",
    html_body: str = "",
    text_body: str = "",
    message_stream: typing.Literal[
        "outbound", "gooey-ai-workflows", "announcements", "billing"
    ] = "outbound",
):
    if is_running_pytest:
        pytest_outbox.append(
            dict(
                from_address=from_address,
                to_address=to_address,
                cc=cc,
                bcc=bcc,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                message_stream=message_stream,
            ),
        )
        return

    r = requests.post(
        "https://api.postmarkapp.com/email",
        headers={
            "X-Postmark-Server-Token": settings.POSTMARK_API_TOKEN,
        },
        json={
            "From": from_address,
            "To": to_address,
            "Cc": cc,
            "Bcc": bcc,
            "Subject": subject,
            # "Tag": "Invitation",
            "HtmlBody": html_body,
            "TextBody": text_body,
            # "ReplyTo": "reply@example.com",
            # "Headers": [{"Name": "CUSTOM-HEADER", "Value": "value"}],
            # "TrackOpens": true,
            # "TrackLinks": "None",
            # "Attachments": [
            #     {
            #         "Name": "readme.txt",
            #         "Content": "dGVzdCBjb250ZW50",
            #         "ContentType": "text/plain",
            #     },
            #     {
            #         "Name": "report.pdf",
            #         "Content": "dGVzdCBjb250ZW50",
            #         "ContentType": "application/octet-stream",
            #     },
            #     {
            #         "Name": "image.jpg",
            #         "ContentID": "cid:image.jpg",
            #         "Content": "dGVzdCBjb250ZW50",
            #         "ContentType": "image/jpeg",
            #     },
            # ],
            # "Metadata": {"color": "blue", "client-id": "12345"},
            "MessageStream": message_stream,
        },
    )
    if r.status_code == 422 and r.json().get("ErrorCode") == 406:
        logger.warning(r.json())
        return
    raise_for_status(r)
