import glom
import requests
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from furl import furl
from starlette.background import BackgroundTasks
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from bots.models import BotIntegration
from daras_ai_v2 import settings, db
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.facebook_bots import WhatsappBot, FacebookBot
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.bots import _on_msg, request_json

router = APIRouter()


@router.get("/__/fb/connect/")
def fb_connect_redirect(request: Request):
    if not request.user or request.user.is_anonymous:
        redirect_url = furl("/login", query_params={"next": request.url})
        return RedirectResponse(str(redirect_url))

    retry_button = f'<a href="{ig_connect_url}">Retry</a>'

    code = request.query_params.get("code")
    if not code:
        return HTMLResponse(
            f"<p>Oh No! Something went wrong here.</p><p>Error: {dict(request.query_params)}</p>"
            + retry_button,
            status_code=400,
        )
    user_access_token = _get_access_token_from_code(code)

    db.get_user_doc_ref(request.user.uid).update({"fb_access_token": user_access_token})

    fb_pages = get_currently_connected_fb_pages(user_access_token)
    if not fb_pages:
        return HTMLResponse(
            f"<p>Please connect with at least one facebook page!</p>" + retry_button,
            status_code=400,
        )

    map_parallel(_subscribe_to_page, fb_pages)
    integrations = BotIntegration.objects.reset_fb_pages_for_user(
        request.user.uid, fb_pages
    )

    page_names = ", ".join(map(str, integrations))
    return HTMLResponse(
        f"Sucessfully Connected to {page_names}! You may now close this page."
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


@router.get("/__/fb/webhook/")
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


@router.post("/__/fb/webhook/")
def fb_webhook(
    background_tasks: BackgroundTasks,
    data: dict = Depends(request_json),
):
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
                    background_tasks.add_task(_on_msg, bot)
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
                    background_tasks.add_task(_on_msg, bot)
    return Response("OK")


fb_connect_redirect_url = str(
    furl(settings.APP_BASE_URL) / router.url_path_for(fb_connect_redirect.__name__)
)

fb_connect_url = str(
    furl(
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
        },
    )
)

ig_connect_url = str(
    furl(
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
        },
    )
)


def _get_access_token_from_code(code: str) -> str:
    r = requests.get(
        "https://graph.facebook.com/v15.0/oauth/access_token",
        params={
            "client_id": settings.FB_APP_ID,
            "redirect_uri": fb_connect_redirect_url,
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
