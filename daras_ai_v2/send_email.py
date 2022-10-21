import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from os.path import basename

import streamlit as st
from decouple import config
from streamlit.runtime.uploaded_file_manager import UploadedFile

from daras_ai.image_input import upload_file_from_bytes


def isImage(data: str) -> bool:
    return data.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif'))


def send_smtp_message(
        *,
        sender,
        to_address,
        cc_address="",
        subject="",
        html_message="",
        text_message="",
        files=None,
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
    # html_message += "<h1>hiiiiii<img width='300px' src='https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/a4691908-511d-11ed-8fcf-921309c00215/out.png'</h1>"
    for f in files or []:
        if type(f) == str:
            if isImage(f):
                html_message += f"<img width='300px', src='{f}'/><br>"
            else:
                html_message += f"<a href='{f}'/><br>"
        elif type(f) == UploadedFile:
            if isImage(f.name):
                url = upload_file_from_bytes(filename=f.name, img_bytes=f.getvalue())
                html_message += f"<img width='300px', src='{url}'/><br>"
                # st.write(url)
            else:
                # TO SEND AS ATTACHMENT
                part = MIMEApplication(
                    f.getvalue(),
                    Name=basename(f.name)
                )
                part['Content-Disposition'] = 'attachment; filename="%s"' % basename(f.name)
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
        smtp_server.sendmail(sender, to_address, msg.as_string())
