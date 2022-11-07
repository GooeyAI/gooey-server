import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from os.path import basename

from decouple import config
from streamlit.runtime.uploaded_file_manager import UploadedFile


def isImage(data: str) -> bool:
    return data.lower().endswith((".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif"))


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

    for img_url in image_urls:
        html_message += f"<br><br><img width='300px', src='{img_url}'/><br>"

    for f in files or []:
        # TO SEND AS ATTACHMENT
        part = MIMEApplication(f.getvalue(), Name=basename(f.name))
        part["Content-Disposition"] = 'attachment; filename="%s"' % basename(f.name)
        msg.attach(part)

    html_message += "<br><br>Regards<br>daras.ai"
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
