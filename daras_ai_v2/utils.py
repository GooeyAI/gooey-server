from daras_ai_v2.send_email import send_email_via_postmark

from random import Random

random = Random()


def email_support_about_reported_run(run_id: str, uid: str, email: str, url: str):
    send_email_via_postmark(
        from_address="devs@gooey.ai",
        to_address="support@gooey.ai",
        subject=f"Reported: Run '{run_id}'",
        html_body=f"""
        <p>

        Reported run:
        <a href="{url}">{url}</a>
        </p>
        <p>

        Reported by:
        <li><b>USER ID:</b> {uid}</li>
        <li><b>EMAIL:</b> {email}</li>
        </p>
        """,
    )
