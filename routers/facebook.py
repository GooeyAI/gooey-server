from functools import partial

import requests
from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from firebase_admin import auth
from furl import furl
from starlette.background import BackgroundTasks
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from daras_ai.face_restoration import map_parallel
from daras_ai_v2 import settings, db

router = APIRouter()


PAGE_NOT_CONNECTED_ERROR = (
    "Looks like you haven't connected this page to a gooey.ai workflow. "
    "Please go to the Integrations Tab and connect this page."
)


@router.post("/__/fb/webhook/")
async def fb_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    print(data)
    object_ = data.get("object")
    for entry in data.get("entry", []):
        for messaging in entry.get("messaging", []):
            message = messaging.get("message")
            if not message:
                continue
            if message.get("is_echo"):
                continue
            background_tasks.add_task(_on_message, object_, messaging)
    return Response("OK")


def _on_message(object_: str, messaging: dict):
    text = messaging["message"].get("text")
    if not text:
        return

    sender_id = messaging["sender"]["id"]
    recipient_id = messaging["recipient"]["id"]

    if object_ == "instagram":
        try:
            snapshot = list(
                db.get_collection_ref(db.FB_PAGES_COLLECTION)
                .where("ig_account_id", "==", recipient_id)
                .limit(1)
                .get()
            )[0]
        except IndexError:
            return
        page_id = snapshot.id
    elif object_ == "page":
        page_id = recipient_id
        snapshot = db.get_fb_page_ref(page_id).get()
    else:
        return

    if not snapshot.exists:
        return
    fb_page = snapshot.to_dict()

    # access_token = db.get_page_access_token(page_id)
    access_token = fb_page.get("access_token")
    if not access_token:
        return

    if object_ == "page":
        _send_messages(
            page_id=page_id,
            access_token=access_token,
            recipient_id=sender_id,
            messages=[
                {"sender_action": "mark_seen"},
                {"sender_action": "typing_on"},
            ],
        )

    from server import call_api, page_map, normalize_slug

    page_slug = fb_page.get("connected_page_slug")
    if not page_slug:
        _send_messages(
            page_id=page_id,
            access_token=access_token,
            recipient_id=sender_id,
            messages=[
                {
                    "messaging_type": "RESPONSE",
                    "message": {"text": PAGE_NOT_CONNECTED_ERROR},
                },
            ],
        )

    page_slug = normalize_slug(page_slug)
    try:
        page_cls = page_map[page_slug]
    except KeyError:
        return
    result = call_api(
        page_cls=page_cls,
        user=auth.get_user(fb_page["uid"]),
        request_body={
            "input_prompt": text,
        },
        query_params=fb_page.get("connected_query_params") or {},
    )
    response_text = result["output"]["output_text"][0]
    response_video = result["output"]["output_video"][0]

    _send_messages(
        page_id=page_id,
        access_token=access_token,
        recipient_id=sender_id,
        messages=[
            {
                "messaging_type": "RESPONSE",
                "message": {
                    "text": response_text,
                },
            },
            {
                "messaging_type": "RESPONSE",
                "message": {
                    "attachment": {
                        "type": "video",
                        "payload": {
                            "url": response_video,
                        },
                    },
                },
            },
        ],
    )


def _send_messages(
    *,
    page_id: str,
    access_token: str,
    recipient_id: str,
    messages: list,
):
    for data in messages:
        r = requests.post(
            f"https://graph.facebook.com/v15.0/{page_id}/messages",
            json={
                "access_token": access_token,
                "recipient": {"id": recipient_id},
                **data,
            },
        )
        print(r.status_code, r.json())


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


@router.get("/__/fb/connect/")
def fb_connect_redirect(request: Request):
    if not request.user:
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

    access_token = _get_access_token_from_code(code)

    r = requests.get(
        "https://graph.facebook.com/v15.0/me/accounts",
        params={
            "access_token": access_token,
            "fields": "id,name,access_token,instagram_business_account{id,username}",
        },
    )
    r.raise_for_status()
    fb_pages = r.json()["data"]

    if not fb_pages:
        return HTMLResponse(
            f"<p>Please connect with at least one facebook page!</p>" + retry_button,
            status_code=400,
        )

    page_docs = map_parallel(partial(_subscribe_to_page, request), fb_pages)
    db.update_pages_for_user(page_docs, request.user.uid)

    page_names = ", ".join(get_page_display_name(page) for _, page in page_docs)
    return HTMLResponse(
        f"Sucessfully Connected to {page_names}! You may now close this page."
    )


def get_page_display_name(page: dict) -> str:
    if page.get("ig_username"):
        return page["ig_username"] + " & " + page["name"]
    else:
        return page["name"]


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
    r.raise_for_status()
    return r.json()["access_token"]


def _subscribe_to_page(request: Request, fb_page: dict) -> (str, dict):
    page_id = fb_page["id"]

    r = requests.post(
        f"https://graph.facebook.com/{page_id}/subscribed_apps",
        params={
            "subscribed_fields": "messages",
            "access_token": fb_page["access_token"],
        },
    )
    r.raise_for_status()

    return page_id, dict(
        uid=request.user.uid,
        name=fb_page["name"],
        access_token=fb_page["access_token"],
        ig_account_id=fb_page.get("instagram_business_account", {}).get("id"),
        ig_username=fb_page.get("instagram_business_account", {}).get("username"),
    )


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
                    "pages_read_engagement",
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
                    "pages_read_engagement",
                ]
            ),
        },
    )
)
