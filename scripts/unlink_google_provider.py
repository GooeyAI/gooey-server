from firebase_admin import auth


def run(*emails):
    """
    Unlink Google provider from Firebase users.

    Usage:
        python manage.py runscript unlink_google_provider --script-args email1@example.com email2@example.com
    """
    if not emails:
        print("No email addresses provided.")
        print(
            "Usage: python manage.py runscript unlink_google_provider --script-args email1@example.com email2@example.com"
        )
        return

    for email in emails:
        try:
            user = auth.get_user_by_email(email)
            auth.update_user(user.uid, providers_to_delete=["google.com"])
            print(f"✓ Unlinked Google provider for {email}")
        except Exception as e:
            print(f"✗ Failed for {email}: {e}")
