import smtplib
import sys
import typing
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from os.path import basename

import requests
from decouple import config

from app_users.models import AppUser
from daras_ai_v2 import settings
from daras_ai_v2.settings import templates
from gooey_ui import UploadedFile


def send_reported_run_email(
    *,
    user: AppUser,
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
    user: AppUser,
    total_credits_consumed: int,
):
    from routers.billing import account_url

    recipeints = "support@gooey.ai, devs@gooey.ai"
    html_body = templates.get_template("low_balance_email.html").render(
        user=user,
        url=account_url,
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
    cc: str = None,
    bcc: str = None,
    subject: str = "",
    html_body: str = "",
    text_body: str = "",
    message_stream: typing.Literal[
        "outbound", "gooey-ai-workflows", "announcements"
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
    assert r.ok, r.text


def send_smtp_message(
    *,
    sender,
    to_address,
    cc_address="",
    subject="",
    html_message="",
    text_message="",
    image_urls: list[str] = None,
    files: list[UploadedFile] = None,
):
    """
    Sends an email by using an Amazon Pinpoint SMTP server.
    :param files: Accepts list of [url]s or [UploadedFile]s
    :param sender: The "From" address. This address must be verified.
    :param to_address: The "To" address. If your account is still in the sandbox,
                       this address must be verified.
    :param cc_address: The "CC" address. If your account is still in the sandbox,
                       this address must be verified.
    :param subject: The subject line of the email.
    :param html_message: The HTML body of the email.
    :param text_message: The email body for recipients with non-HTML email clients.
    """
    # Create message container. The correct MIME type is multipart/alternative.
    msg = MIMEMultipart("alternative")
    msg["From"] = sender  # sender
    msg["To"] = to_address
    msg["Cc"] = cc_address
    msg["Subject"] = subject
    msg.attach(MIMEText(text_message, "plain"))
    to = [to_address] + cc_address.split(",")

    for img_url in image_urls or []:
        html_message += f"<br><br><img width='300px', src='{img_url}'/><br>"

    for f in files or []:
        # TO SEND AS ATTACHMENT
        part = MIMEApplication(f.getvalue(), Name=basename(f.name))
        part["Content-Disposition"] = 'attachment; filename="%s"' % basename(f.name)
        msg.attach(part)

    msg.attach(MIMEText(html_message, "html"))

    with smtplib.SMTP(
        config("AWS_SMTP_SERVER"), config("AWS_SMTP_PORT")
    ) as smtp_server:
        smtp_server.ehlo()
        smtp_server.starttls()
        # smtplib docs recommend calling ehlo() before and after starttls()
        smtp_server.ehlo()
        smtp_server.login(config("AWS_SMTP_USERNAME"), config("AWS_SMTP_PASSWORD"))
        # Uncomment the next line to send SMTP server responses to stdout.
        # smtp_server.set_debuglevel(1)
        smtp_server.sendmail(sender, to, msg.as_string())
