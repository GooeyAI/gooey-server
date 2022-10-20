import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from os.path import basename

import streamlit as st
from decouple import config


def send_smtp_message(
        smtp_server, smtp_username,
        smtp_password, sender, to_address, cc_address,
        subject_text, html_message, text_message, files=None):
    """
    Sends an email by using an Amazon Pinpoint SMTP server.

    :param smtp_server: An smtplib SMTP session.
    :param smtp_username: The username to use to connect to the SMTP server.
    :param smtp_password: The password to use to connect to the SMTP server.
    :param sender: The "From" address. This address must be verified.
    :param to_address: The "To" address. If your account is still in the sandbox,
                       this address must be verified.
    :param cc_address: The "CC" address. If your account is still in the sandbox,
                       this address must be verified.
    :param subject_text: The subject line of the email.
    :param html_message: The HTML body of the email.
    :param text_message: The email body for recipients with non-HTML email clients.
    """
    # Create message container. The correct MIME type is multipart/alternative.
    msg = MIMEMultipart('alternative')
    msg['From'] = "events@dara.network"  # sender
    msg['To'] = to_address
    msg['Cc'] = cc_address
    msg['Subject'] = subject_text
    msg.attach(MIMEText(html_message, 'html'))
    msg.attach(MIMEText(text_message, 'plain'))
    for f in files or []:
        part = MIMEApplication(
            f.getvalue(),
            Name=basename(f.name)
        )
        part['Content-Disposition'] = 'attachment; filename="%s"' % basename(f.name)
        msg.attach(part)

    smtp_server.ehlo()
    smtp_server.starttls()
    # smtplib docs recommend calling ehlo() before and after starttls()
    smtp_server.ehlo()
    smtp_server.login(smtp_username, smtp_password)
    # Uncomment the next line to send SMTP server responses to stdout.
    # smtp_server.set_debuglevel(1)
    smtp_server.sendmail(sender, to_address, msg.as_string())


def send_email():
    print([to_email, from_email, files])
    try:
        with smtplib.SMTP(config("AWS_SMTP_SERVER"), config("AWS_SMTP_PORT")) as smtp_server:
            send_smtp_message(
                smtp_server, config("AWS_SMTP_USERNAME"), config("AWS_SMTP_PASSWORD"), from_email, to_email,
                "", subject, "", body, files=files)
    except Exception:
        st.error(body="Couldn't send message.", icon="⚠️")
        raise
    else:
        st.success(body="Email sent", icon="✅")


st.write("# Send email")
with st.form(key="send_email", clear_on_submit=False):
    to_email = st.text_input(label="To")
    from_email = st.text_input(label="From")
    subject = st.text_input(label="Subject")
    body = st.text_area(label="Body")
    files = st.file_uploader(label="Attachments",
                             accept_multiple_files=True
                             )
    submitted = st.form_submit_button("Send")
    if submitted:
        send_email()
