import requests

from daras_ai_v2 import settings


async def construct_contact(user_data):
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


async def trigger_sign_up_email_automation(access_token, created_contact, data):
    response = requests.post(
        settings.WIX_API_EVENTS_REPORT_URL,
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


async def get_wix_access_token() -> str:
    refresh_token_data = {
        "grant_type": "refresh_token",
        "client_id": settings.WIX_APP_CLIENT_ID,
        "client_secret": settings.WIX_APP_CLIENT_SECRET,
        "refresh_token": settings.WIX_EMAIL_APP_REFRESH_TOKEN,
    }
    response = requests.post(settings.WIX_APP_OAUTH_URL, json=refresh_token_data)
    response.raise_for_status()
    data = response.json()
    return data.get("access_token")
