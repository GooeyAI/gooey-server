import requests
from fastapi.responses import RedirectResponse
from furl import furl
import json
from starlette.background import BackgroundTasks
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from bots.models import BotIntegration, Platform, SavedRun, PublishedRun
from daras_ai_v2 import settings, db
from daras_ai_v2.bots import msg_handler
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.facebook_bots import WhatsappBot, FacebookBot
from daras_ai_v2.fastapi_tricks import fastapi_request_json
from daras_ai_v2.functional import map_parallel
from recipes.VideoBots import connect
from routers.custom_api_router import CustomAPIRouter

app = CustomAPIRouter()


@app.get("/__/fb/connect_whatsapp/")
def fb_connect_whatsapp_redirect(request: Request):
    if not request.user or request.user.is_anonymous:
        redirect_url = furl("/login", query_params={"next": request.url})
        return RedirectResponse(str(redirect_url))

    connection_state = json.loads(request.query_params.get("state", "{}"))
    current_run_id = connection_state.get("current_run_id", None)
    published_run_id = connection_state.get("published_run_id", None)
    retry_button = (
        f'<a href="{wa_connect_url(current_run_id, published_run_id)}">Retry</a>'
    )
    current_run = SavedRun.objects.get(run_id=current_run_id)
    published_run = PublishedRun.objects.filter(
        published_run_id=published_run_id
    ).first()

    code = request.query_params.get("code")
    if not code:
        return HTMLResponse(
            f"<p>Oh No! Something went wrong here.</p><p>Error: {dict(request.query_params)}</p>"
            + retry_button,
            status_code=400,
        )
    user_access_token = _get_access_token_from_code(code, wa_connect_redirect_url)

    # get WABA ID
    r = requests.get(
        f"https://graph.facebook.com/v19.0/debug_token?input_token={user_access_token}&access_token={settings.FB_APP_ID}|{settings.FB_APP_SECRET}",
        # headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
    )
    r.raise_for_status()
    # {'data': {'app_id': 'XXXX', 'type': 'SYSTEM_USER', 'application': 'gooey.ai', 'data_access_expires_at': 0, 'expires_at': 0, 'is_valid': True, 'issued_at': 1708634537, 'scopes': ['whatsapp_business_management', 'whatsapp_business_messaging', 'public_profile'], 'granular_scopes': [{'scope': 'whatsapp_business_management', 'target_ids': ['XXXX']}, {'scope': 'whatsapp_business_messaging', 'target_ids': ['XXXX']}], 'user_id': 'XXXX'}}
    waba_obj = r.json()["data"]
    user_id = waba_obj["user_id"]
    waba_id = waba_obj["granular_scopes"][0]["target_ids"][0]

    # get WABA details
    r = requests.get(
        f"https://graph.facebook.com/v19.0/{waba_id}?access_token={user_access_token}",
    )
    r.raise_for_status()
    # {'id': 'XXXX', 'name': 'Test', 'timezone_id': '1', 'message_template_namespace': 'XXXX'}
    waba_details = r.json()
    account_name = waba_details["name"]
    message_template_namespace = waba_details["message_template_namespace"]

    # get WABA phone numbers
    r = requests.get(
        f"https://graph.facebook.com/v19.0/{waba_id}/phone_numbers?access_token={user_access_token}",
    )
    r.raise_for_status()
    # {'data': [{'verified_name': 'XXXX', 'code_verification_status': 'VERIFIED', 'display_phone_number': 'XXXX', 'quality_rating': 'UNKNOWN', 'platform_type': 'NOT_APPLICABLE', 'throughput': {'level': 'NOT_APPLICABLE'}, 'last_onboarded_time': '2024-02-22T20:42:16+0000', 'id': 'XXXX'}], 'paging': {'cursors': {'before': 'XXXX', 'after': 'XXXX'}}}
    phone_numbers = r.json()["data"]

    redirect = None
    for phone_number in phone_numbers:
        business_name = phone_number["verified_name"]
        display_phone_number = phone_number["display_phone_number"]
        phone_number_id = phone_number["id"]

        options = dict(
            billing_account_uid=request.user.uid,
            platform=Platform.WHATSAPP,
            name=f"{business_name} - {account_name}",
            wa_phone_number=display_phone_number,
            wa_business_access_token=user_access_token,
            wa_business_waba_id=waba_id,
            wa_business_user_id=user_id,
            wa_business_name=business_name,
            wa_business_account_name=account_name,
            wa_business_message_template_namespace=message_template_namespace,
        )
        bi, created = BotIntegration.objects.get_or_create(
            wa_phone_number_id=phone_number_id, defaults=options
        )
        if not created:
            BotIntegration.objects.filter(id=bi.id).update(**options)
        else:
            # register the phone number for Whatsapp
            r = requests.post(
                f"https://graph.facebook.com/v19.0/{phone_number_id}/register?access_token={user_access_token}",
                json={
                    "messaging_product": "whatsapp",
                    "pin": settings.WHATSAPP_2FA_PIN,
                },
            )
            r.raise_for_status()

        # subscribe our app to weebhooks for WABA
        r = requests.post(
            f"https://graph.facebook.com/v19.0/{waba_id}/subscribed_apps?access_token={user_access_token}",
            json={
                "override_callback_uri": str(
                    furl(settings.APP_BASE_URL) / app.url_path_for(fb_webhook.__name__)
                ),
                "verify_token": settings.FB_WEBHOOK_TOKEN,
            },
        )
        r.raise_for_status()

        redirect = connect(bi, current_run, published_run)

    return (
        RedirectResponse(url=redirect.url, status_code=redirect.status_code)
        if redirect
        else HTMLResponse("No phone numbers found!" + retry_button)
    )


@app.get("/__/fb/connect/")
def fb_connect_redirect(request: Request):
    if not request.user or request.user.is_anonymous:
        redirect_url = furl("/login", query_params={"next": request.url})
        return RedirectResponse(str(redirect_url))

    connection_state = json.loads(request.query_params.get("state", "{}"))
    current_run_id: str | None = connection_state.get("current_run_id", None)
    published_run_id: str | None = connection_state.get("published_run_id", None)
    retry_button = (
        f'<a href="{fb_connect_url(current_run_id, published_run_id)}">Retry</a>'
    )
    current_run = SavedRun.objects.get(run_id=current_run_id)
    published_run = PublishedRun.objects.filter(
        published_run_id=published_run_id
    ).first()

    code = request.query_params.get("code")
    if not code:
        return HTMLResponse(
            f"<p>Oh No! Something went wrong here.</p><p>Error: {dict(request.query_params)}</p>"
            + retry_button,
            status_code=400,
        )
    user_access_token = _get_access_token_from_code(code, fb_connect_redirect_url)

    db.get_user_doc_ref(request.user.uid).set(
        {"fb_access_token": user_access_token}, merge=True
    )

    fb_pages = get_currently_connected_fb_pages(user_access_token)
    if not fb_pages:
        return HTMLResponse(
            f"<p>Please connect with at least one facebook page!</p>" + retry_button,
            status_code=400,
        )

    # only connect to pages that are not already connected
    fb_pages = [
        fb_page
        for fb_page in fb_pages
        if BotIntegration.objects.filter(
            fb_page_id=fb_page["id"]
        )  # this will need to change if we ever add instagram
        .exclude(saved_run__isnull=True)
        .count()
        == 0
    ]

    map_parallel(_subscribe_to_page, fb_pages)
    integrations = BotIntegration.objects.reset_fb_pages_for_user(
        request.user.uid, fb_pages
    )

    redirect = None
    for integration in integrations:
        redirect = connect(integration, current_run, published_run)

    return (
        RedirectResponse(url=redirect.url, status_code=redirect.status_code)
        if redirect
        else HTMLResponse("No pages found!" + retry_button)
    )


def get_currently_connected_fb_pages(user_access_token):
    r = requests.get(
        "https://graph.facebook.com/v15.0/me/accounts",
        params={
            "access_token": user_access_token,
            "fields": "id,name,access_token,instagram_business_account{id,username}",
        },
    )
    raise_for_status(r)
    fb_pages = r.json()["data"]
    return fb_pages


@app.get("/__/fb/webhook/")
async def fb_webhook_verify(request: Request):
    mode = request.query_params.get("hub.mode")
    verify_token = request.query_params.get("hub.verify_token")
    if (
        mode == "subscribe"
        and verify_token
        and verify_token == settings.FB_WEBHOOK_TOKEN
    ):
        return Response(request.query_params.get("hub.challenge"))
    else:
        return Response(status_code=403)


@app.post("/__/fb/webhook/")
def fb_webhook(
    background_tasks: BackgroundTasks,
    data: dict = fastapi_request_json,
):
    import glom

    print("fb_webhook:", data)
    object_name = data.get("object")
    for entry in data.get("entry", []):
        match object_name:
            # handle whatsapp messages
            case "whatsapp_business_account":
                value = glom.glom(entry, "changes.0.value", default={})
                for message in value.get("messages", []):
                    try:
                        bot = WhatsappBot(message, value["metadata"])
                    except ValueError:
                        continue
                    background_tasks.add_task(msg_handler, bot)
            # handle fb/insta messages
            case "instagram" | "page":
                for messaging in entry.get("messaging", []):
                    message = messaging.get("message")
                    if not message:
                        continue
                    # handle echo of bot sent messags
                    if message.get("is_echo"):
                        continue
                    try:
                        bot = FacebookBot(object_name, messaging)
                    except ValueError:
                        continue
                    background_tasks.add_task(msg_handler, bot)
    return Response("OK")


wa_connect_redirect_url = (
    furl(
        settings.APP_BASE_URL,
    )
    / app.url_path_for(fb_connect_whatsapp_redirect.__name__)
).tostr()


def wa_connect_url(current_run_id: str | None, published_run_id: str | None) -> str:
    return furl(
        "https://www.facebook.com/v18.0/dialog/oauth",
        query_params={
            "client_id": settings.FB_APP_ID,
            "display": "page",
            "redirect_uri": wa_connect_redirect_url,
            "response_type": "code",
            "config_id": settings.FB_WHATSAPP_CONFIG_ID,
            "state": json.dumps(
                dict(current_run_id=current_run_id, published_run_id=published_run_id)
            ),
        },
    ).tostr()


fb_connect_redirect_url = (
    furl(
        settings.APP_BASE_URL,
    )
    / app.url_path_for(fb_connect_redirect.__name__)
).tostr()


def fb_connect_url(current_run_id: str | None, published_run_id: str | None) -> str:
    return furl(
        "https://www.facebook.com/dialog/oauth",
        query_params={
            "client_id": settings.FB_APP_ID,
            "display": "page",
            "redirect_uri": fb_connect_redirect_url,
            "response_type": "code",
            "scope": ",".join(
                [
                    "pages_messaging",
                    "pages_manage_metadata",
                    "pages_show_list",
                ]
            ),
            "state": json.dumps(
                dict(current_run_id=current_run_id, published_run_id=published_run_id)
            ),
        },
    ).tostr()


def ig_connect_url(current_run_id: str | None, published_run_id: str | None) -> str:
    return furl(
        "https://www.facebook.com/dialog/oauth",
        query_params={
            "client_id": settings.FB_APP_ID,
            "display": "page",
            "extras": '{"setup":{"channel":"IG_API_ONBOARDING"}}',
            "redirect_uri": fb_connect_redirect_url,
            "response_type": "code",
            "scope": ",".join(
                [
                    "instagram_basic",
                    "instagram_manage_messages",
                    "pages_messaging",
                    "pages_manage_metadata",
                    "pages_show_list",
                ]
            ),
            "state": json.dumps(
                dict(current_run_id=current_run_id, published_run_id=published_run_id)
            ),
        },
    ).tostr()


def _get_access_token_from_code(code: str, redirect_uri: str) -> str:
    r = requests.get(
        "https://graph.facebook.com/v15.0/oauth/access_token",
        params={
            "client_id": settings.FB_APP_ID,
            "redirect_uri": redirect_uri,
            "client_secret": settings.FB_APP_SECRET,
            "code": code,
        },
    )
    raise_for_status(r)
    return r.json()["access_token"]


def _subscribe_to_page(fb_page: dict):
    """Subscribe to the page's messages"""
    page_id = fb_page["id"]
    r = requests.post(
        f"https://graph.facebook.com/{page_id}/subscribed_apps",
        params={
            "subscribed_fields": "messages",
            "access_token": fb_page["access_token"],
        },
    )
    raise_for_status(r)
