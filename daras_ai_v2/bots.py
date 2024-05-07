import mimetypes
import traceback
import typing
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from fastapi import HTTPException
from furl import furl
from pydantic import BaseModel, Field
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
from daras_ai_v2.asr import run_google_translate
from daras_ai_v2.base import BasePage, RecipeRunState, StateKeys
from daras_ai_v2.language_model import CHATML_ROLE_USER, CHATML_ROLE_ASSISTANT
from daras_ai_v2.vector_search import doc_url_to_file_metadata
from gooey_ui.pubsub import realtime_subscribe
from gooeysite.bg_db_conn import db_middleware, get_celery_result_db_safe
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


class ButtonPressed(BaseModel):
    button_id: str = Field(
        description="The ID of the button that was pressed by the user"
    )
    context_msg_id: str = Field(
        description="The message ID of the context message on which the button was pressed"
    )


class BotInterface:
    platform: Platform
    bot_id: str
    user_id: str
    convo: Conversation
    input_type: typing.Literal[
        "text", "audio", "video", "image", "document", "interactive"
    ]
    user_msg_id: str = None
    can_update_message: bool = False

    page_cls: typing.Type[BasePage] | None
    query_params: dict
    language: str
    billing_account_uid: str
    show_feedback_buttons: bool = False
    streaming_enabled: bool = False
    input_glossary: str | None = None
    output_glossary: str | None = None

    recipe_run_state = RecipeRunState.starting
    run_status = "Starting..."

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

    def get_interactive_msg_info(self) -> ButtonPressed:
        raise NotImplementedError("This bot does not support interactive messages.")

    def on_run_created(
        self, page: BasePage, result: "celery.result.AsyncResult", run_id: str, uid: str
    ):
        pass

    def send_run_status(self, update_msg_id: str | None) -> str | None:
        pass

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
            self.language = saved_run.state.get("user_language")
        elif bi.saved_run:
            self.page_cls = Workflow(bi.saved_run.workflow).page_cls
            self.query_params = self.page_cls.clean_query_params(
                example_id=bi.saved_run.example_id,
                run_id=bi.saved_run.run_id,
                uid=bi.saved_run.uid,
            )
            self.input_glossary = bi.saved_run.state.get("input_glossary_document")
            self.output_glossary = bi.saved_run.state.get("output_glossary_document")
            self.language = bi.saved_run.state.get("user_language")
        else:
            self.page_cls = None
            self.query_params = {}

        self.billing_account_uid = bi.billing_account_uid
        if bi.user_language and bi.user_language != "en":
            self.language = bi.user_language
        self.show_feedback_buttons = bi.show_feedback_buttons
        self.streaming_enabled = bi.streaming_enabled


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
def msg_handler(bot: BotInterface):
    recieved_time: datetime = timezone.now()
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
    input_text = (bot.get_input_text() or "").strip()
    input_audio = None
    input_images = None
    input_documents = None
    match bot.input_type:
        # handle button press
        case "interactive":
            _handle_interactive_msg(bot)
            return
        case "image":
            input_images = bot.get_input_images()
            if not input_images:
                raise HTTPException(
                    status_code=400, detail="No image found in request."
                )
        case "document":
            input_documents = bot.get_input_documents()
            if not input_documents:
                raise HTTPException(
                    status_code=400, detail="No documents found in request."
                )
            filenames = ", ".join(
                furl(url.strip("/")).path.segments[-1] for url in input_documents
            )
            input_text = f"Files: {filenames}\n\n{input_text}"
        case "audio" | "video":
            input_audio = bot.get_input_audio()
            if not input_audio:
                bot.send_msg(text=DEFAULT_RESPONSE)
                return
        case "text":
            if not input_text:
                bot.send_msg(text=DEFAULT_RESPONSE)
                return
        case _:
            bot.send_msg(text=INVALID_INPUT_FORMAT.format(bot.input_type))
            return
    # handle reset keyword
    if input_text.lower() == RESET_KEYWORD:
        # record the reset time so we don't send context
        bot.convo.reset_at = timezone.now()
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
            input_audio=input_audio,
            recieved_time=recieved_time,
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
    input_audio: str | None,
    input_documents: list[str] | None,
    input_text: str,
    recieved_time: datetime,
):
    # get latest messages for context
    saved_msgs = bot.convo.msgs_as_llm_context()

    # # mock testing
    # result = _mock_api_output(input_text)
    body = {
        "input_prompt": input_text,
        "input_audio": input_audio,
        "input_images": input_images,
        "input_documents": input_documents,
        "messages": saved_msgs,
    }
    if bot.language and bot.language != "en":
        body["user_language"] = bot.language
    page, result, run_id, uid = submit_api_call(
        page_cls=bot.page_cls,
        user=billing_account_user,
        request_body=body,
        query_params=bot.query_params,
    )
    bot.on_run_created(page, result, run_id, uid)

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
                bot.recipe_run_state = page.get_run_state(state)
                bot.run_status = state.get(StateKeys.run_status) or ""
                # check for errors
                if bot.recipe_run_state == RecipeRunState.failed:
                    err_msg = state.get(StateKeys.error_msg)
                    bot.send_msg(text=ERROR_MSG.format(err_msg))
                    return  # abort
                if bot.recipe_run_state != RecipeRunState.running:
                    break  # we're done running, stop streaming
                text = state.get("output_text") and state.get("output_text")[0]
                if not text:
                    # if no text, send the run status as text
                    update_msg_id = bot.send_run_status(update_msg_id=update_msg_id)
                    continue  # no text, wait for the next update
                streaming_done = state.get("finish_reason")
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
                    break  # we're done streaming, stop the loop

    # wait for the celery task to finish
    get_celery_result_db_safe(result)
    # get the final state from db
    sr = page.run_doc_sr(run_id, uid)
    state = sr.to_dict()
    bot.recipe_run_state = page.get_run_state(state)
    bot.run_status = state.get(StateKeys.run_status) or ""
    # check for errors
    err_msg = state.get(StateKeys.error_msg)
    if err_msg:
        bot.send_msg(text=ERROR_MSG.format(err_msg))
        return

    text = state.get("output_text") and state.get("output_text")[0]
    audio = state.get("output_audio") and state.get("output_audio")[0]
    video = state.get("output_video") and state.get("output_video")[0]
    documents = state.get("output_documents")
    # check for empty response
    if not (text or audio or video or documents or buttons):
        bot.send_msg(text=DEFAULT_RESPONSE)
        return
    # if in-place updates are enabled, update the message, otherwise send the remaining text
    if text and not bot.can_update_message:
        text = text[last_idx:]
    # send the response to the user if there is any remaining
    if text or audio or video or documents or buttons:
        update_msg_id = bot.send_msg(
            text=text or None,
            audio=audio or None,
            video=video or None,
            documents=documents or None,
            buttons=buttons,
            update_msg_id=update_msg_id,
        )

    # save msgs to db
    _save_msgs(
        bot=bot,
        input_images=input_images,
        input_documents=input_documents,
        input_text=input_text,
        platform_msg_id=sent_msg_id or update_msg_id,
        response=VideoBotsPage.ResponseModel.parse_obj(state),
        saved_run=sr,
        received_time=recieved_time,
    )


def _save_msgs(
    bot: BotInterface,
    input_images: list[str] | None,
    input_documents: list[str] | None,
    input_text: str,
    platform_msg_id: str | None,
    response: VideoBotsPage.ResponseModel,
    saved_run: SavedRun,
    received_time: datetime,
):
    # create messages for future context
    user_msg = Message(
        platform_msg_id=bot.user_msg_id,
        conversation=bot.convo,
        role=CHATML_ROLE_USER,
        content=response.raw_input_text,
        display_content=input_text,
        response_time=timezone.now() - received_time,
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
        saved_run=saved_run,
        response_time=timezone.now() - received_time,
    )
    # save the messages & attachments
    # note that its important to save the user_msg and assistant_msg together because we use get_next_by_created_at in our code
    with transaction.atomic():
        user_msg.save()
        for attachment in attachments:
            attachment.metadata.save()
            attachment.save()
        assistant_msg.save()


def _handle_interactive_msg(bot: BotInterface):
    try:
        button = bot.get_interactive_msg_info()
    except NotImplementedError as e:
        bot.send_msg(text=ERROR_MSG.format(e))
        return
    match button.button_id:
        # handle feedback button press
        case ButtonIds.feedback_thumbs_up | ButtonIds.feedback_thumbs_down:
            try:
                context_msg = Message.objects.get(
                    platform_msg_id=button.context_msg_id, conversation=bot.convo
                )
            except Message.DoesNotExist as e:
                traceback.print_exc()
                capture_exception(e)
                # send error msg as repsonse
                bot.send_msg(text=ERROR_MSG.format(e))
                return
            if button.button_id == ButtonIds.feedback_thumbs_up:
                rating = Feedback.Rating.RATING_THUMBS_UP
                # bot.convo.state = ConvoState.ASK_FOR_FEEDBACK_THUMBS_UP
                # response_text = FEEDBACK_THUMBS_UP_MSG
            else:
                rating = Feedback.Rating.RATING_THUMBS_DOWN
                # bot.convo.state = ConvoState.ASK_FOR_FEEDBACK_THUMBS_DOWN
                # response_text = FEEDBACK_THUMBS_DOWN_MSG
            response_text = FEEDBACK_CONFIRMED_MSG.format(
                bot_name=str(bot.convo.bot_integration.name)
            )
            bot.convo.save()
            # save the feedback
            Feedback.objects.create(message=context_msg, rating=rating)
            # send a confirmation msg + post click buttons
            bot.send_msg(
                text=response_text,
                # buttons=_feedback_post_click_buttons(),
                should_translate=True,
            )

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
