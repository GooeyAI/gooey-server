import traceback

import glom
import requests
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import RedirectResponse
from firebase_admin import auth
from furl import furl
from sentry_sdk import capture_exception
from starlette.background import BackgroundTasks
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from bots.models import (
    BotIntegration,
    Platform,
    Message,
    Conversation,
    Feedback,
    SavedRun,
)
from daras_ai_v2 import settings, db
from daras_ai_v2.all_pages import Workflow
from daras_ai_v2.asr import AsrModels
from daras_ai_v2.facebook_bots import WhatsappBot, FacebookBot, BotInterface
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.language_model import CHATML_ROLE_USER, CHATML_ROLE_ASSISSTANT
from gooeysite.bg_db_conn import bg_db_task

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


FEEDBACK_MSG = (
    "🙏 Thanks! Your feedback helps us make {bot_name} better. How else can I help you?"
)


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


async def request_json(request: Request):
    return await request.json()


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
    r.raise_for_status()
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
    r.raise_for_status()


@bg_db_task
def _on_msg(bot: BotInterface):
    if not bot.page_cls:
        bot.send_msg(text=PAGE_NOT_CONNECTED_ERROR)
        return
    # mark message as read
    bot.mark_read()
    # get the attached billing account
    billing_account_user = auth.get_user(bot.billing_account_uid)
    # get the user's input
    match bot.input_type:
        # handle button press
        case "interactive":
            try:
                button_id = bot.input_message["interactive"]["button_reply"]["id"]
                context_msg_id = bot.input_message["context"]["id"]
                context_msg = Message.objects.get(wa_msg_id=context_msg_id)
            except (KeyError, Message.DoesNotExist) as e:
                bot.send_msg(text=ERROR_MSG.format(e))
                return
            bot_name = str(context_msg.conversation.bot_integration)
            match button_id:
                case ButtonIds.feedback_thumbs_up:
                    bot.send_msg(text=FEEDBACK_MSG.format(bot_name=bot_name))
                    rating = Feedback.RATING_THUMBS_UP
                case ButtonIds.feedback_thumbs_down:
                    bot.send_msg(text=FEEDBACK_MSG.format(bot_name=bot_name))
                    rating = Feedback.RATING_THUMBS_DOWN
                case _:
                    # not sure what button was pressed, ignore
                    bot.send_msg(text=FEEDBACK_MSG.format(bot_name="this bot"))
                    return
            Feedback.objects.create(message=context_msg, rating=rating)
            return
        case "audio":
            try:
                from recipes.asr import AsrPage
                from server import call_api

                # run asr
                asr_lang = None
                match bot.language.lower():
                    case "am":
                        selected_model = AsrModels.usm.name
                        asr_lang = "am-et"
                    case "hi":
                        selected_model = AsrModels.nemo_hindi.name
                    case "te":
                        selected_model = AsrModels.whisper_telugu_large_v2.name
                    case _:
                        selected_model = AsrModels.whisper_large_v2.name
                result = call_api(
                    page_cls=AsrPage,
                    user=billing_account_user,
                    request_body={
                        "documents": [bot.get_input_audio()],
                        "selected_model": selected_model,
                        "google_translate_target": None,
                        "asr_lang": asr_lang,
                    },
                    query_params={},
                )
            except HTTPException as e:
                traceback.print_exc()
                capture_exception(e)
                # send error message
                bot.send_msg(text=ERROR_MSG.format(e))
                return
            else:
                # set the asr output as the input text
                input_text = result["output"]["output_text"][0].strip()
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
        bot.convo.messages.all().delete()
        msgs_to_save = []
        # let the user know we've reset
        response_text = RESET_MSG
        response_audio = None
        response_video = None
    else:
        # # mock testing
        # msgs_to_save, response_audio, response_text, response_video = _echo(
        #     bot, input_text
        # )
        try:
            # make API call to gooey bots to get the response
            response_text, response_audio, response_video, msgs_to_save = _process_msg(
                page_cls=bot.page_cls,
                api_user=billing_account_user,
                query_params=bot.query_params,
                convo=bot.convo,
                input_text=input_text,
                user_language=bot.language,
            )
        except HTTPException as e:
            traceback.print_exc()
            capture_exception(e)
            # send error msg as repsonse
            bot.send_msg(text=ERROR_MSG.format(e))
            return
    # this really shouldn't happen, but just in case it does, we should have a nice message for the user
    response_text = response_text or DEFAULT_RESPONSE
    # send the response to the user
    msg_id = bot.send_msg(
        text=response_text,
        audio=response_audio,
        video=response_video,
        buttons=_feedback_buttons() if bot.show_feedback_buttons else None,
    )
    if not msgs_to_save:
        return
    if bot.platform == Platform.WHATSAPP and msg_id:
        msgs_to_save[-1].wa_msg_id = msg_id
    for msg in msgs_to_save:
        msg.save()


class ButtonIds:
    feedback_thumbs_up = "FEEDBACK_THUMBS_UP"
    feedback_thumbs_down = "FEEDBACK_THUMBS_DOWN"


def _feedback_buttons():
    return [
        {
            "type": "reply",
            "reply": {"id": ButtonIds.feedback_thumbs_up, "title": "👍🏾"},
        },
        {
            "type": "reply",
            "reply": {"id": ButtonIds.feedback_thumbs_down, "title": "👎🏾"},
        },
    ]


def _process_msg(
    *,
    page_cls,
    api_user: auth.UserRecord,
    query_params: dict,
    convo: Conversation,
    input_text: str,
    user_language: str,
) -> tuple[str, str | None, str | None, list[Message]]:
    # # mock testing
    # result = _mock_api_output(input_text)

    # get latest messages for context (upto 100)
    saved_msgs = list(
        reversed(
            convo.messages.order_by("-created_at").values("role", "content")[:100],
        ),
    )
    # call the api with provided input
    result = {
        "output": {
            "output_text": ["Hello, world! https://www.youtube.com/"],
            "raw_output_text": ["Hello, world! https://www.youtube.com/"],
        }
    }
    # result = call_api(
    #     page_cls=page_cls,
    #     user=api_user,
    #     request_body={
    #         "input_prompt": input_text,
    #         "messages": saved_msgs,
    #         "user_language": user_language,
    #     },
    #     query_params=query_params,
    # )
    # extract response video/audio/text
    try:
        response_video = result["output"]["output_video"][0]
    except (KeyError, IndexError):
        response_video = None
    try:
        response_audio = result["output"]["output_audio"][0]
    except (KeyError, IndexError):
        response_audio = None
    raw_input_text = result["output"]["raw_input_text"]
    output_text = result["output"]["output_text"][0]
    raw_output_text = result["output"]["raw_output_text"][0]
    response_text = result["output"]["output_text"][0]
    # save new messages for future context
    msgs_to_save = [
        Message(
            conversation=convo,
            role=CHATML_ROLE_USER,
            content=raw_input_text,
            display_content=input_text,
        ),
        Message(
            conversation=convo,
            role=CHATML_ROLE_ASSISSTANT,
            content=raw_output_text,
            display_content=output_text,
            saved_run=SavedRun.objects.get_or_create(
                workflow=Workflow.VIDEOBOTS,
                **furl(result.get("url", "")).query.params,
            )[0],
        ),
    ]
    return response_text, response_audio, response_video, msgs_to_save


def _echo(bot, input_text):
    response_text = f"You said ```{input_text}```\nhttps://www.youtube.com/"
    if bot.get_input_audio():
        response_audio = [bot.get_input_audio()]
    else:
        response_audio = None
    if bot.get_input_video():
        response_video = [bot.get_input_video()]
    else:
        response_video = None
    msgs_to_save = []
    return msgs_to_save, response_audio, response_text, response_video


def _mock_api_output(input_text):
    return {
        "output": {
            "raw_input_text": input_text,
            "output_text": [f"echo: ```{input_text}```\nhttps://www.youtube.com/"],
            "raw_output_text": [f"echo: ```{input_text}```\nhttps://www.youtube.com/"],
        }
    }
