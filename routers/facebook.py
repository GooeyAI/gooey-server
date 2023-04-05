from functools import partial

import glom
import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from firebase_admin import auth
from furl import furl
from sentry_sdk import capture_exception
from starlette.background import BackgroundTasks
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from daras_ai.face_restoration import map_parallel
from daras_ai_v2 import settings, db
from daras_ai_v2.asr import run_google_translate
from daras_ai_v2.facebook_bots import WhatsappBot, FacebookBot, BotInterface
from daras_ai_v2.language_model import CHATML_ROLE_USER, CHATML_ROLE_ASSISSTANT

router = APIRouter()

PAGE_NOT_CONNECTED_ERROR = (
    "Looks like you haven't connected this page to a gooey.ai workflow. "
    "Please go to the Integrations Tab and connect this page."
)


RESET_KEYWORD = "reset"
RESET_MSG = "♻️ Sure! Let's start fresh. How can I help you?"

DEFAULT_RESPONSE = "🤔 Well that was Unexpected! I lost my train of thought. Could you please try again?."

INVALID_INPUT_FORMAT = (
    "⚠️ Sorry! I don't understand {} messsages. Please try with text or audio."
)

AUDIO_ASR_CONFIRMATION = """
I heard: “{}”
Working on your answer…
""".strip()

ERROR_MSG = """
`{0!r}`

⚠️ Sorry, I ran into an error while processing your request. Please try again, or type "Reset" to start over.
""".strip()


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
    user_access_token = _get_access_token_from_code(code)

    db.get_user_doc_ref(request.user.uid).update({"fb_access_token": user_access_token})

    fb_pages = get_currently_connected_fb_pages(user_access_token)
    if not fb_pages:
        return HTMLResponse(
            f"<p>Please connect with at least one facebook page!</p>" + retry_button,
            status_code=400,
        )

    page_docs = map_parallel(
        lambda fb_page: _subscribe_to_page(request, user_access_token, fb_page),
        fb_pages,
    )

    db.update_pages_for_user(page_docs, request.user.uid)

    page_names = ", ".join(get_page_display_name(page) for _, page in page_docs)
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
    r.raise_for_status()
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
async def fb_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
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


def _subscribe_to_page(
    request: Request, user_access_token: str, fb_page: dict
) -> (str, dict):
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
        platform="fb",
        page_id=page_id,
        uid=request.user.uid,
        name=fb_page["name"],
        user_access_token=user_access_token,
        page_access_token=fb_page["access_token"],
        ig_account_id=fb_page.get("instagram_business_account", {}).get("id"),
        ig_username=fb_page.get("instagram_business_account", {}).get("username"),
    )


def _on_msg(bot: BotInterface):
    if not bot.page_cls:
        bot.send_msg(text=PAGE_NOT_CONNECTED_ERROR)
        return
    # mark message as read
    bot.mark_read()
    # get the attached billing account
    billing_account = auth.get_user(bot.billing_account_uid)
    # get the user's input
    match bot.input_type:
        case "audio":
            try:
                from recipes.asr import AsrPage
                from server import call_api

                # run asr
                if bot.language == "hi":
                    selected_model = "nemo_hindi"
                else:
                    selected_model = "nemo_english"
                result = call_api(
                    page_cls=AsrPage,
                    user=billing_account,
                    request_body={
                        "documents": [bot.get_input_audio()],
                        "selected_model": selected_model,
                        "google_translate_target": None,
                    },
                    query_params={},
                )
            except HTTPException as e:
                capture_exception(e)
                # send error message
                bot.send_msg(text=ERROR_MSG.format(e))
                return
            else:
                # get input text, and let the caller produce a repsonse
                input_text = result["output"]["output_text"][0]
                # send confirmation of asr
                bot.send_msg(text=AUDIO_ASR_CONFIRMATION.format(input_text))
        case "text":
            input_text = bot.get_input_text()
        case _:
            bot.send_msg(text=INVALID_INPUT_FORMAT.format(bot.input_type))
            return
    # handle reset keyword
    if input_text.strip().lower() == RESET_KEYWORD:
        # clear saved messages
        saved_msgs = []
        # let the user know we've reset
        response_text = RESET_MSG
        response_audio = None
        response_video = None
    # make API call to gooey bots to get the response
    else:
        # translate response text, but don't save the translated text
        if bot.language != "en":
            input_text = run_google_translate(
                texts=[input_text],
                google_translate_target="en",
            )[0]
        try:
            response_text, response_audio, response_video, saved_msgs = _process_msg(
                page_cls=bot.page_cls,
                api_user=billing_account,
                query_params=bot.query_params,
                bot_id=bot.bot_id,
                user_id=bot.user_id,
                input_text=input_text,
            )
        except HTTPException as e:
            # handle exceptions
            capture_exception(e)
            # send error msg as repsonse
            bot.send_msg(text=ERROR_MSG.format(e))
            return
        # translate response text, but don't save the translated text
        if bot.language != "en":
            response_text = run_google_translate(
                texts=[response_text],
                google_translate_target=bot.language,
            )[0]
    # this really shouldn't happen, but just in case it does, we should have a nice message for the user
    response_text = response_text or DEFAULT_RESPONSE
    # send the response to the user
    bot.send_msg(text=response_text, audio=response_audio, video=response_video)
    # save the messages for future context
    db.save_user_msgs(
        bot_id=bot.bot_id,
        user_id=bot.user_id,
        messages=saved_msgs,
        platform="wa",
    )


def _process_msg(
    *,
    page_cls,
    api_user: auth.UserRecord,
    query_params: dict,
    bot_id: str,
    user_id: str,
    input_text: str,
) -> tuple[str, str | None, str | None, list[dict]]:
    from server import call_api

    # initialize variables
    response_audio = None
    response_video = None
    # get saved messages for context
    saved_msgs = db.get_user_msgs(bot_id=bot_id, user_id=user_id)
    # call the api with provided input
    result = call_api(
        page_cls=page_cls,
        user=api_user,
        request_body={
            "input_prompt": input_text,
            "messages": saved_msgs,
        },
        query_params=query_params,
    )
    # extract response video/audio/text
    try:
        response_video = result["output"]["output_video"][0]
    except (KeyError, IndexError):
        pass
    try:
        response_audio = result["output"]["output_audio"][0]
    except (KeyError, IndexError):
        pass
    response_text = result["output"]["output_text"][0]
    # save new messages for context
    saved_msgs += [
        {"role": CHATML_ROLE_USER, "content": input_text},
        {"role": CHATML_ROLE_ASSISSTANT, "content": response_text},
    ]
    return response_text, response_audio, response_video, saved_msgs
