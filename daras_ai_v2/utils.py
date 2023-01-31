from daras_ai_v2.send_email import send_email_via_postmark

from random import Random

random = Random()


def email_support_about_reported_run(
    uid: str,
    email: str,
    url: str,
    recipe_name: str,
    report_type: str,
    reason_for_report: str,
):
    send_email_via_postmark(
        from_address="devs@gooey.ai",
        to_address="support@gooey.ai",
        subject=f"{email} reported {report_type} on {recipe_name}",
        html_body=f"""
        <p>

        Reported run:
        <a href="{url}">{url}</a>
        </p>
        Recipe Name: {recipe_name} <br>
        Report Type: {report_type} <br>
        Reason for Report: {reason_for_report} <br>
        <p>

        Reported by:
        <li><b>USER ID:</b> {uid}</li>
        <li><b>EMAIL:</b> {email}</li>
        </p>
        """,
    )
