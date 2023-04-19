import requests

from daras_ai_v2 import settings
WIX_API_CREATE_CONTACTS_ENDPOINT = "https://www.wixapis.com/contacts/v4/contacts"
WIX_API_QUERY_CONTACTS_ENDPOINT = "https://www.wixapis.com/contacts/v4/contacts/query"
WIX_API_EVENTS_REPORT_ENDPOINT = "https://www.wixapis.com/automations/v1/events/report"
WIX_APP_OAUTH_ENDPOINT = "https://www.wixapis.com/oauth/access"


def add_to_wix_contact(user_data: dict):
    email = user_data.get("email")
    # No email-> phone number signin
    if not email:
        return
    # Check if wix contact already exists
    wix_contact = check_wix_contact_exists(email)
    if wix_contact:
        return
    # Create wix contact
    contact_data =construct_contact(user_data)
    response = requests.post(
        WIX_API_CREATE_CONTACTS_ENDPOINT,
        headers={
            "Authorization": settings.WIX_API_KEY,
            "wix-site-id": settings.WIX_SITE_ID,
        },
        json=contact_data,
    )
    response.raise_for_status()
    created_contact = response.json().get("contact")
    access_token = get_wix_access_token()
    trigger_sign_up_email_automation(access_token, created_contact, user_data)


def construct_contact(user_data):
    return {
        "info": {
            "name": {
                "first": user_data.get("name"),
            },
            "emails": {
                "items": [
                    {
                        "tag": "MAIN",
                        "email": user_data.get("email"),
                    },
                ],
            },
        }
    }


def trigger_sign_up_email_automation(access_token, created_contact, data):
    response = requests.post(
        WIX_API_EVENTS_REPORT_ENDPOINT,
        headers={
            "Authorization": access_token,
        },
        json={
            "triggerKey": settings.WIX_AUTOMATION_TRIGGER_KEY,
            "payload": {
                "email": data.get("email"),
                "contact_id": created_contact.get("id"),
            },
        },
    )
    response.raise_for_status()


def get_wix_access_token() -> str:
    refresh_token_data = {
        "grant_type": "refresh_token",
        "client_id": settings.WIX_APP_CLIENT_ID,
        "client_secret": settings.WIX_APP_CLIENT_SECRET,
        "refresh_token": settings.WIX_EMAIL_APP_REFRESH_TOKEN,
    }
    response = requests.post(WIX_APP_OAUTH_ENDPOINT, json=refresh_token_data)
    response.raise_for_status()
    data = response.json()
    return data.get("access_token")


def check_wix_contact_exists(email) -> bool:
    response = requests.post(
        WIX_API_QUERY_CONTACTS_ENDPOINT,
        headers={
            "Authorization": settings.WIX_API_KEY,
            "wix-site-id": settings.WIX_SITE_ID,
        },
        json={"search": email},
    )
    response.raise_for_status()
    data = response.json()
    for contact in data.get("contacts"):
        primary_info = contact.get("primaryInfo")
        if primary_info.get("email") == email:
            return True
    return False
