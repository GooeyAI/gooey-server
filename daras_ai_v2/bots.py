import mimetypes
import traceback
import typing
from urllib.parse import parse_qs

from django.db import transaction
from fastapi import HTTPException, Request
from furl import furl
from sentry_sdk import capture_exception

from app_users.models import AppUser
from bots.models import (
    Platform,
    Message,
    Conversation,
    Feedback,
    SavedRun,
    ConvoState,
    Workflow,
    MessageAttachment,
)
from daras_ai_v2.asr import AsrModels, run_google_translate
from daras_ai_v2.base import BasePage, RecipeRunState, StateKeys
from daras_ai_v2.language_model import CHATML_ROLE_USER, CHATML_ROLE_ASSISTANT
from daras_ai_v2.vector_search import doc_url_to_file_metadata
from gooey_ui.pubsub import realtime_subscribe
from gooeysite.bg_db_conn import db_middleware
from recipes.VideoBots import VideoBotsPage, ReplyButton
from routers.api import submit_api_call

PAGE_NOT_CONNECTED_ERROR = (
    "💔 Looks like you haven't connected this page to a gooey.ai workflow. "
    "Please go to the Integrations Tab and connect this page."
)
RESET_KEYWORD = "reset"
RESET_MSG = "♻️ Sure! Let's start fresh. How can I help you?"

DEFAULT_RESPONSE = (
    "🤔🤖 Well that was Unexpected! I seem to be lost. Could you please try again?."
)

INVALID_INPUT_FORMAT = (
    "⚠️ Sorry! I don't understand {} messsages. Please try with text or audio."
)

AUDIO_ASR_CONFIRMATION = """
🎧 I heard: “{}”
Working on your answer…
""".strip()

ERROR_MSG = """
`{}`

⚠️ Sorry, I ran into an error while processing your request. Please try again, or type "Reset" to start over.
""".strip()

FEEDBACK_THUMBS_UP_MSG = "🎉 What did you like about my response?"
FEEDBACK_THUMBS_DOWN_MSG = "🤔 What was the issue with the response? How could it be improved? Please send me an voice note or text me."
FEEDBACK_CONFIRMED_MSG = (
    "🙏 Thanks! Your feedback helps us make {bot_name} better. How else can I help you?"
)

TAPPED_SKIP_MSG = "🌱 Alright. What else can I help you with?"

SLACK_MAX_SIZE = 3000


async def request_json(request: Request):
    return await request.json()


async def request_urlencoded_body(request: Request):
    return parse_qs((await request.body()).decode("utf-8"))


class BotInterface:
    input_message: dict
    platform: Platform
    billing_account_uid: str
    page_cls: typing.Type[BasePage] | None
    query_params: dict
    bot_id: str
    user_id: str
    input_type: str
    language: str
    show_feedback_buttons: bool = False
    streaming_enabled: bool = False
    can_update_message: bool = False
    convo: Conversation
    recieved_msg_id: str = None
    input_glossary: str | None = None
    output_glossary: str | None = None

    def send_msg(
        self,
        *,
        text: str | None = None,
        audio: str = None,
        video: str = None,
        buttons: list[ReplyButton] = None,
        documents: list[str] = None,
        should_translate: bool = False,
        update_msg_id: str = None,
    ) -> str | None:
        raise NotImplementedError

    def mark_read(self):
        raise NotImplementedError

    def get_input_text(self) -> str | None:
        raise NotImplementedError

    def get_input_audio(self) -> str | None:
        raise NotImplementedError

    def get_input_images(self) -> list[str] | None:
        raise NotImplementedError

    def get_input_documents(self) -> list[str] | None:
        raise NotImplementedError

    def nice_filename(self, mime_type: str) -> str:
        ext = mimetypes.guess_extension(mime_type) or ""
        return f"{self.platform.name}_{self.input_type}_from_{self.user_id}_to_{self.bot_id}{ext}"

    def _unpack_bot_integration(self):
        bi = self.convo.bot_integration
        if bi.published_run:
            self.page_cls = Workflow(bi.published_run.workflow).page_cls
            self.query_params = self.page_cls.clean_query_params(
                example_id=bi.published_run.published_run_id,
                run_id="",
                uid="",
            )
            saved_run = bi.published_run.saved_run
            self.input_glossary = saved_run.state.get("input_glossary_document")
            self.output_glossary = saved_run.state.get("output_glossary_document")
        elif bi.saved_run:
            self.page_cls = Workflow(bi.saved_run.workflow).page_cls
            self.query_params = self.page_cls.clean_query_params(
                example_id=bi.saved_run.example_id,
                run_id=bi.saved_run.run_id,
                uid=bi.saved_run.uid,
            )
            self.input_glossary = bi.saved_run.state.get("input_glossary_document")
            self.output_glossary = bi.saved_run.state.get("output_glossary_document")
        else:
            self.page_cls = None
            self.query_params = {}

        self.billing_account_uid = bi.billing_account_uid
        self.language = bi.user_language
        self.show_feedback_buttons = bi.show_feedback_buttons
        self.streaming_enabled = bi.streaming_enabled

    def get_interactive_msg_info(self) -> tuple[str, str]:
        raise NotImplementedError("This bot does not support interactive messages.")


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
        "url": "https://gooey.ai?example_id=mock-api-example",
        "output": {
            "input_text": input_text,
            "raw_input_text": input_text,
            "raw_output_text": [f"echo: ```{input_text}```\nhttps://www.youtube.com/"],
            "output_text": [f"echo: ```{input_text}```\nhttps://www.youtube.com/"],
        },
    }


@db_middleware
def _on_msg(bot: BotInterface):
    speech_run = None
    input_images = None
    input_documents = None
    if not bot.page_cls:
        bot.send_msg(text=PAGE_NOT_CONNECTED_ERROR)
        return
    if bot.input_type != "interactive":
        # mark message as read
        bot.mark_read()
    # get the attached billing account
    billing_account_user = AppUser.objects.get_or_create_from_uid(
        bot.billing_account_uid
    )[0]
    # get the user's input
    # print("input type:", bot.input_type)
    match bot.input_type:
        # handle button press
        case "interactive":
            _handle_interactive_msg(bot)
            return
        case "audio" | "video":
            try:
                result = _handle_audio_msg(billing_account_user, bot)
                speech_run = result.get("url")
            except HTTPException as e:
                traceback.print_exc()
                capture_exception(e)
                # send error message
                bot.send_msg(text=ERROR_MSG.format(e))
                return
            else:
                # set the asr output as the input text
                input_text = result["output"]["output_text"][0].strip()
                if not input_text:
                    bot.send_msg(text=DEFAULT_RESPONSE)
                    return
                # send confirmation of asr
                bot.send_msg(text=AUDIO_ASR_CONFIRMATION.format(input_text))
        case "image":
            input_images = bot.get_input_images()
            if not input_images:
                raise HTTPException(
                    status_code=400, detail="No image found in request."
                )
            input_text = (bot.get_input_text() or "").strip()
        case "document":
            input_documents = bot.get_input_documents()
            if not input_documents:
                raise HTTPException(
                    status_code=400, detail="No documents found in request."
                )
            filenames = ", ".join(
                furl(url.strip("/")).path.segments[-1] for url in input_documents
            )
            input_text = (bot.get_input_text() or "").strip()
            input_text = f"Files: {filenames}\n\n{input_text}"
        case "text":
            input_text = (bot.get_input_text() or "").strip()
            if not input_text:
                bot.send_msg(text=DEFAULT_RESPONSE)
                return
        case _:
            bot.send_msg(text=INVALID_INPUT_FORMAT.format(bot.input_type))
            return
    # handle reset keyword
    if input_text.lower() == RESET_KEYWORD:
        # clear saved messages
        bot.convo.messages.all().delete()
        # reset convo state
        bot.convo.state = ConvoState.INITIAL
        bot.convo.save()
        # let the user know we've reset
        bot.send_msg(text=RESET_MSG)
    # handle feedback submitted
    elif bot.convo.state in [
        ConvoState.ASK_FOR_FEEDBACK_THUMBS_UP,
        ConvoState.ASK_FOR_FEEDBACK_THUMBS_DOWN,
    ]:
        _handle_feedback_msg(bot, input_text)
    else:
        _process_and_send_msg(
            billing_account_user=billing_account_user,
            bot=bot,
            input_images=input_images,
            input_documents=input_documents,
            input_text=input_text,
            speech_run=speech_run,
        )


def _handle_feedback_msg(bot: BotInterface, input_text):
    try:
        last_feedback = Feedback.objects.filter(
            message__conversation=bot.convo
        ).latest()
    except Feedback.DoesNotExist as e:
        bot.send_msg(text=ERROR_MSG.format(e))
        return
    # save the feedback
    last_feedback.text = input_text
    # translate feedback to english
    last_feedback.text_english = " ".join(
        run_google_translate([input_text], "en", glossary_url=bot.input_glossary)
    )
    last_feedback.save()
    # send back a confimation msg
    bot.show_feedback_buttons = False  # don't show feedback for this confirmation
    bot_name = str(bot.convo.bot_integration.name)
    # reset convo state
    bot.convo.state = ConvoState.INITIAL
    bot.convo.save()
    # let the user know we've received their feedback
    bot.send_msg(
        text=FEEDBACK_CONFIRMED_MSG.format(bot_name=bot_name),
        should_translate=True,
    )


def _process_and_send_msg(
    *,
    billing_account_user: AppUser,
    bot: BotInterface,
    input_images: list[str] | None,
    input_documents: list[str] | None,
    input_text: str,
    speech_run: str | None,
):
    # get latest messages for context (upto 100)
    saved_msgs = bot.convo.messages.all().as_llm_context()

    # # mock testing
    # result = _mock_api_output(input_text)
    page, result, run_id, uid = submit_api_call(
        page_cls=bot.page_cls,
        user=billing_account_user,
        request_body={
            "input_prompt": input_text,
            "input_images": input_images,
            "input_documents": input_documents,
            "messages": saved_msgs,
            "user_language": bot.language,
        },
        query_params=bot.query_params,
    )

    if bot.show_feedback_buttons:
        buttons = _feedback_start_buttons()
    else:
        buttons = None

    update_msg_id = None  # this is the message id to update during streaming
    sent_msg_id = None  # this is the message id to record in the db
    last_idx = 0  # this is the last index of the text sent to the user
    if bot.streaming_enabled:
        # subscribe to the realtime channel for updates
        channel = page.realtime_channel_name(run_id, uid)
        with realtime_subscribe(channel) as realtime_gen:
            for state in realtime_gen:
                run_state = page.get_run_state(state)
                run_status = state.get(StateKeys.run_status) or ""
                # check for errors
                if run_state == RecipeRunState.failed:
                    err_msg = state.get(StateKeys.error_msg)
                    bot.send_msg(text=ERROR_MSG.format(err_msg))
                    return  # abort
                if run_state != RecipeRunState.running:
                    break  # we're done running, abort
                text = state.get("output_text") and state.get("output_text")[0]
                if not text:
                    # if no text, send the run status
                    if bot.can_update_message:
                        update_msg_id = bot.send_msg(
                            text=run_status, update_msg_id=update_msg_id
                        )
                    continue  # no text, wait for the next update
                streaming_done = not run_status.lower().startswith("streaming")
                # send the response to the user
                if bot.can_update_message:
                    update_msg_id = bot.send_msg(
                        text=text.strip() + "...",
                        update_msg_id=update_msg_id,
                        buttons=buttons if streaming_done else None,
                    )
                    last_idx = len(text)
                else:
                    next_chunk = text[last_idx:]
                    last_idx = len(text)
                    if not next_chunk:
                        continue  # no chunk, wait for the next update
                    update_msg_id = bot.send_msg(
                        text=next_chunk,
                        buttons=buttons if streaming_done else None,
                    )
                if streaming_done and not bot.can_update_message:
                    # if we send the buttons, this is the ID we need to record in the db for lookups later when the button is pressed
                    sent_msg_id = update_msg_id
                    # don't show buttons again
                    buttons = None
                if streaming_done:
                    break  # we're done streaming, abort

    # wait for the celery task to finish
    result.get(disable_sync_subtasks=False)
    # get the final state from db
    state = page.run_doc_sr(run_id, uid).to_dict()
    # check for errors
    err_msg = state.get(StateKeys.error_msg)
    if err_msg:
        bot.send_msg(text=ERROR_MSG.format(err_msg))
        return

    text = (state.get("output_text") and state.get("output_text")[0]) or ""
    audio = state.get("output_audio") and state.get("output_audio")[0]
    video = state.get("output_video") and state.get("output_video")[0]
    documents = state.get("output_documents") or []
    # check for empty response
    if not (text or audio or video or documents or buttons):
        bot.send_msg(text=DEFAULT_RESPONSE)
        return
    # if in-place updates are enabled, update the message, otherwise send the remaining text
    if not bot.can_update_message:
        text = text[last_idx:]
    # send the response to the user if there is any remaining
    if text or audio or video or documents or buttons:
        update_msg_id = bot.send_msg(
            text=text,
            audio=audio,
            video=video,
            documents=documents,
            buttons=buttons,
            update_msg_id=update_msg_id,
        )

    # save msgs to db
    _save_msgs(
        bot=bot,
        input_images=input_images,
        input_documents=input_documents,
        input_text=input_text,
        speech_run=speech_run,
        platform_msg_id=sent_msg_id or update_msg_id,
        response=VideoBotsPage.ResponseModel.parse_obj(state),
        url=page.app_url(run_id=run_id, uid=uid),
    )


def _save_msgs(
    bot: BotInterface,
    input_images: list[str] | None,
    input_documents: list[str] | None,
    input_text: str,
    speech_run: str | None,
    platform_msg_id: str | None,
    response: VideoBotsPage.ResponseModel,
    url: str,
):
    # create messages for future context
    user_msg = Message(
        platform_msg_id=bot.recieved_msg_id,
        conversation=bot.convo,
        role=CHATML_ROLE_USER,
        content=response.raw_input_text,
        display_content=input_text,
        saved_run=SavedRun.objects.get_or_create(
            workflow=Workflow.ASR, **furl(speech_run).query.params
        )[0]
        if speech_run
        else None,
    )
    attachments = []
    for f_url in (input_images or []) + (input_documents or []):
        metadata = doc_url_to_file_metadata(f_url)
        attachments.append(
            MessageAttachment(message=user_msg, url=f_url, metadata=metadata)
        )
    assistant_msg = Message(
        platform_msg_id=platform_msg_id,
        conversation=bot.convo,
        role=CHATML_ROLE_ASSISTANT,
        content=response.raw_output_text and response.raw_output_text[0],
        display_content=response.output_text and response.output_text[0],
        saved_run=SavedRun.objects.get_or_create(
            workflow=Workflow.VIDEO_BOTS, **furl(url).query.params
        )[0],
    )
    # save the messages & attachments
    with transaction.atomic():
        user_msg.save()
        for attachment in attachments:
            attachment.metadata.save()
            attachment.save()
        assistant_msg.save()


def _handle_interactive_msg(bot: BotInterface):
    try:
        button_id, context_msg_id = bot.get_interactive_msg_info()
    except NotImplementedError as e:
        bot.send_msg(text=ERROR_MSG.format(e))
        return
    match button_id:
        # handle feedback button press
        case ButtonIds.feedback_thumbs_up | ButtonIds.feedback_thumbs_down:
            try:
                context_msg = Message.objects.get(platform_msg_id=context_msg_id)
            except Message.DoesNotExist as e:
                traceback.print_exc()
                capture_exception(e)
                # send error msg as repsonse
                bot.send_msg(text=ERROR_MSG.format(e))
                return
            if button_id == ButtonIds.feedback_thumbs_up:
                rating = Feedback.Rating.RATING_THUMBS_UP
                bot.convo.state = ConvoState.ASK_FOR_FEEDBACK_THUMBS_UP
                response_text = FEEDBACK_THUMBS_UP_MSG
            else:
                rating = Feedback.Rating.RATING_THUMBS_DOWN
                bot.convo.state = ConvoState.ASK_FOR_FEEDBACK_THUMBS_DOWN
                response_text = FEEDBACK_THUMBS_DOWN_MSG
            bot.convo.save()
        # handle skip
        case ButtonIds.action_skip:
            bot.send_msg(text=TAPPED_SKIP_MSG, should_translate=True)
            # reset state
            bot.convo.state = ConvoState.INITIAL
            bot.convo.save()
            return
        # not sure what button was pressed, ignore
        case _:
            bot_name = str(bot.convo.bot_integration.name)
            bot.send_msg(
                text=FEEDBACK_CONFIRMED_MSG.format(bot_name=bot_name),
                should_translate=True,
            )
            # reset state
            bot.convo.state = ConvoState.INITIAL
            bot.convo.save()
            return
    # save the feedback
    Feedback.objects.create(message=context_msg, rating=rating)
    # send a confirmation msg + post click buttons
    bot.send_msg(
        text=response_text,
        buttons=_feedback_post_click_buttons(),
        should_translate=True,
    )


def _handle_audio_msg(billing_account_user, bot: BotInterface):
    from recipes.asr import AsrPage
    from routers.api import call_api

    input_audio = bot.get_input_audio()
    if not input_audio:
        raise HTTPException(status_code=400, detail="No audio found in request.")

    # run asr
    language = None
    match bot.language.lower():
        case "am":
            selected_model = AsrModels.usm.name
            language = "am-et"
        case "hi":
            selected_model = AsrModels.nemo_hindi.name
        case "te":
            selected_model = AsrModels.whisper_telugu_large_v2.name
        case "bho":
            selected_model = AsrModels.vakyansh_bhojpuri.name
        case "en":
            selected_model = AsrModels.usm.name
        case _:
            selected_model = AsrModels.whisper_large_v2.name

    result = call_api(
        page_cls=AsrPage,
        user=billing_account_user,
        request_body={
            "documents": [input_audio],
            "selected_model": selected_model,
            "google_translate_target": None,
            "language": language,
        },
        query_params={},
    )
    return result


class ButtonIds:
    action_skip = "ACTION_SKIP"
    feedback_thumbs_up = "FEEDBACK_THUMBS_UP"
    feedback_thumbs_down = "FEEDBACK_THUMBS_DOWN"


def _feedback_post_click_buttons() -> list[ReplyButton]:
    """
    Buttons to show after the user has clicked on a feedback button
    """
    return [
        {"id": ButtonIds.action_skip, "title": "🔀 Skip"},
    ]


def _feedback_start_buttons() -> list[ReplyButton]:
    """
    Buttons to show for collecting feedback after the bot has sent a response
    """
    return [
        {"id": ButtonIds.feedback_thumbs_up, "title": "👍🏾"},
        {"id": ButtonIds.feedback_thumbs_down, "title": "👎🏽"},
    ]
