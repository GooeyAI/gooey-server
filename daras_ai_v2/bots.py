import mimetypes
import typing
from datetime import datetime

import gooey_gui as gui
import requests
from django.db import transaction
from django.utils import timezone
from fastapi import HTTPException
from pydantic import BaseModel, Field

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
    BotIntegration,
)
from daras_ai_v2 import settings
from daras_ai_v2.asr import run_google_translate, should_translate_lang
from daras_ai_v2.base import BasePage, RecipeRunState, StateKeys
from daras_ai_v2.csv_lines import csv_encode_row, csv_decode_row
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.language_model import CHATML_ROLE_USER, CHATML_ROLE_ASSISTANT
from daras_ai_v2.search_ref import SearchReference
from daras_ai_v2.vector_search import doc_url_to_file_metadata
from gooeysite.bg_db_conn import db_middleware
from recipes.VideoBots import VideoBotsPage, ReplyButton
from routers.api import submit_api_call
from workspaces.models import Workspace

PAGE_NOT_CONNECTED_ERROR = (
    "💔 Looks like you haven't connected this page to a gooey.ai workflow. "
    "Please go to the Integrations Tab and connect this page."
)
RESET_KEYWORDS = {"reset", "new", "restart", "clear"}
RESET_MSG = "♻️ Sure! Let's start fresh. How can I help you?"

DEFAULT_RESPONSE = (
    "🤔🤖 Well that was Unexpected! I seem to be lost. Could you please try again?."
)

INVALID_INPUT_FORMAT = (
    "⚠️ Sorry! I don't understand {} messsages. Please try with text or audio."
)

ERROR_MSG = """
⚠️ Sorry, I ran into an error while processing your request. Please try again, or send "Reset" to start over.

`{}`
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
    button_title: str | None = Field(
        description="The title of the button that was pressed by the user"
    )


class BotInterface:
    platform: Platform
    bot_id: str
    user_id: str
    convo: Conversation
    bi: BotIntegration
    saved_run: SavedRun | None = None
    input_type: typing.Literal[
        "text", "audio", "video", "image", "document", "interactive"
    ]
    user_msg_id: str | None = None
    can_update_message: bool = False

    page_cls: typing.Type[BasePage] | None = None
    query_params: dict
    user_language: str | None = None
    workspace: Workspace
    current_user: AppUser
    show_feedback_buttons: bool = False
    streaming_enabled: bool = False
    input_glossary: str | None = None
    output_glossary: str | None = None

    recipe_run_state = RecipeRunState.starting
    run_status = "Starting..."

    request_overrides: dict | None = None

    def __init__(self):
        assert self.convo, "A conversation must be set"

        self.bi = self.convo.bot_integration
        if self.bi.published_run:
            self.saved_run = self.bi.published_run.saved_run
            self.page_cls = Workflow(self.bi.published_run.workflow).page_cls
            self.query_params = dict(
                example_id=self.bi.published_run.published_run_id,
            )
        elif self.bi.saved_run:
            self.saved_run = self.bi.saved_run
            self.page_cls = Workflow(self.saved_run.workflow).page_cls
            self.query_params = self.page_cls.clean_query_params(
                example_id=self.saved_run.example_id,
                run_id=self.saved_run.run_id,
                uid=self.saved_run.uid,
            )

        if self.saved_run:
            self.input_glossary = self.saved_run.state.get("input_glossary_document")
            self.output_glossary = self.saved_run.state.get("output_glossary_document")
            user_language = self.saved_run.state.get("user_language")
        else:
            user_language = None

        if should_translate_lang(self.bi.user_language):
            self.user_language = self.bi.user_language
        elif should_translate_lang(user_language):
            self.user_language = user_language

        self.workspace = self.bi.workspace
        self.current_user = self.bi.created_by

        self.show_feedback_buttons = self.bi.show_feedback_buttons
        self.streaming_enabled = self.bi.streaming_enabled

    def send_msg(
        self,
        *,
        text: str | None = None,
        audio: list[str] | None = None,
        video: list[str] | None = None,
        send_feedback_buttons: bool = False,
        documents: list[str] | None = None,
        update_msg_id: str | None = None,
        should_translate: bool = False,
    ) -> str | None:
        """
        Send a message response to the user using the bot's platform API

        :param text: The text to send
        :param audio: The audio URL to send
        :param video: The video URL to send
        :param send_feedback_buttons: Whether to send feedback buttons with the message
        :param documents: The document URLs to send
        :param update_msg_id: The message ID of the message to update in-place
        :param should_translate: The messages from the saved run itself should automatically be translated,
            so we don't need to translate them again. This flag is for when we need to translate hardcoded text
        :return: The message ID of the sent message
        """
        if should_translate:
            text = self.translate_response(text)

        buttons, text, disable_feedback = parse_bot_html(text)
        if disable_feedback:
            send_feedback_buttons = False

        if buttons and send_feedback_buttons:
            self._send_msg(
                text=text,
                audio=audio,
                video=video,
                buttons=buttons,
                documents=documents,
                update_msg_id=update_msg_id,
            )
            text = ""

        if send_feedback_buttons:
            buttons = _feedback_start_buttons()

        return self._send_msg(
            text=text,
            audio=audio,
            video=video,
            buttons=buttons,
            documents=documents,
            update_msg_id=update_msg_id,
        )

    def _send_msg(
        self,
        *,
        text: str | None = None,
        audio: list[str] | None = None,
        video: list[str] | None = None,
        buttons: list[ReplyButton] | None = None,
        documents: list[str] | None = None,
        update_msg_id: str | None = None,
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

    def get_location_info(self) -> dict:
        raise NotImplementedError("This bot does not support location messages.")

    def on_run_created(self, sr: "SavedRun"):
        pass

    def send_run_status(
        self, update_msg_id: str | None, references: list[SearchReference] | None = None
    ) -> str | None:
        pass

    def nice_filename(self, mime_type: str) -> str:
        ext = mimetypes.guess_extension(mime_type) or ""
        return f"{self.platform.name}_{self.input_type}_from_{self.user_id}_to_{self.bot_id}{ext}"

    def translate_response(self, text: str | None) -> str:
        if text and self.user_language:
            return run_google_translate(
                [text], self.user_language, glossary_url=self.output_glossary
            )[0]
        else:
            return text or ""


def parse_bot_html(text: str | None) -> tuple[list[ReplyButton], str, bool]:
    from pyquery import PyQuery as pq

    if not text:
        return [], text, False
    doc = pq(f"<root>{text}</root>")
    buttons = []
    disable_feedback = False
    for idx, btn in enumerate(doc("button") or []):
        if "disable_feedback" in (btn.attrib.get("gui-action") or ""):
            disable_feedback = True
        buttons.append(
            ReplyButton(
                # parsed by _handle_interactive_msg
                id=csv_encode_row(
                    idx + 1,
                    btn.attrib.get("gui-target") or "input_prompt",
                    btn.attrib.get("gui-action"),
                    # title must be the last item because it might get truncated
                    btn.text or "",
                ),
                title=btn.text or "",
            )
        )

    text = "\n\n".join(
        s for elem in doc.contents() if isinstance(elem, str) and (s := elem.strip())
    )

    return buttons, text, disable_feedback


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


def msg_handler(bot: BotInterface):
    try:
        _msg_handler(bot)
    except Exception as e:
        # send error msg as response
        bot.send_msg(text=ERROR_MSG.format(e))
        raise


@db_middleware
def _msg_handler(bot: BotInterface):
    recieved_time: datetime = timezone.now()
    if not bot.page_cls:
        bot.send_msg(text=PAGE_NOT_CONNECTED_ERROR)
        return
    if bot.input_type != "interactive":
        # mark message as read
        bot.mark_read()
    # get the user's input
    # print("input type:", bot.input_type)
    input_text = (bot.get_input_text() or "").strip()
    input_audio = None
    input_images = None
    input_documents = None
    match bot.input_type:
        # handled button press
        case "interactive":
            if _handle_interactive_msg(bot):
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
        case "audio" | "video":
            input_audio = bot.get_input_audio()
            if not input_audio:
                bot.send_msg(text=DEFAULT_RESPONSE)
                return
        case "location":
            input_location = bot.get_location_info()
            if not input_location:
                bot.send_msg(text=DEFAULT_RESPONSE)
                return
            input_text = _handle_location_msg(input_location)
        case "text":
            if not input_text:
                bot.send_msg(text=DEFAULT_RESPONSE)
                return
        case _:
            bot.send_msg(text=INVALID_INPUT_FORMAT.format(bot.input_type))
            return
    # handle reset keyword
    if input_text.lower().strip("/ ") in RESET_KEYWORDS:
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
            workspace=bot.workspace,
            current_user=bot.current_user,
            bot=bot,
            input_images=input_images,
            input_documents=input_documents,
            input_text=input_text,
            input_audio=input_audio,
            recieved_time=recieved_time,
        )


def _handle_feedback_msg(bot: BotInterface, input_text):
    last_feedback = Feedback.objects.filter(message__conversation=bot.convo).latest()
    # save the feedback
    last_feedback.text = input_text
    # translate feedback to english
    last_feedback.text_english = " ".join(
        run_google_translate([input_text], "en", glossary_url=bot.input_glossary)
    )
    last_feedback.save()
    # send back a confirmation msg
    bot.show_feedback_buttons = False  # don't show feedback for this confirmation
    bot_name = str(bot.bi.name)
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
    workspace: Workspace,
    current_user: AppUser,
    bot: BotInterface,
    input_images: list[str] | None,
    input_audio: str | None,
    input_documents: list[str] | None,
    input_text: str,
    recieved_time: datetime,
):
    # get latest messages for context
    saved_msgs = bot.convo.msgs_for_llm_context()

    system_vars, system_vars_schema = build_system_vars(bot.convo, bot.user_msg_id)
    state = bot.saved_run.state
    variables = (state.get("variables") or {}) | system_vars
    variables_schema = (state.get("variables_schema") or {}) | system_vars_schema
    body = dict(
        input_prompt=input_text,
        input_audio=input_audio,
        input_images=input_images,
        input_documents=input_documents,
        messages=saved_msgs,
        variables=variables,
        variables_schema=variables_schema,
    )
    if bot.user_language:
        body["user_language"] = bot.user_language
    if bot.request_overrides:
        body.update(bot.request_overrides)
        try:
            variables.update(bot.request_overrides["variables"])
        except KeyError:
            pass
    result, sr = submit_api_call(
        page_cls=bot.page_cls,
        query_params=bot.query_params,
        workspace=workspace,
        current_user=current_user,
        request_body=body,
    )
    bot.on_run_created(sr)

    send_feedback_buttons = bot.show_feedback_buttons

    update_msg_id = None  # this is the message id to update during streaming
    sent_msg_id = None  # this is the message id to record in the db
    last_idx = 0  # this is the last index of the text sent to the user
    if bot.streaming_enabled:
        # subscribe to the realtime channel for updates
        channel = bot.page_cls.realtime_channel_name(sr.run_id, sr.uid)
        with gui.realtime_subscribe(channel) as realtime_gen:
            for state in realtime_gen:
                bot.recipe_run_state = bot.page_cls.get_run_state(state)
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
                    update_msg_id = bot.send_run_status(
                        update_msg_id=update_msg_id, references=state.get("references")
                    )
                    continue  # no text, wait for the next update
                streaming_done = state.get("finish_reason")
                # send the response to the user
                if bot.can_update_message:
                    update_msg_id = bot.send_msg(
                        text=text.strip() + "...",
                        update_msg_id=update_msg_id,
                        send_feedback_buttons=streaming_done and send_feedback_buttons,
                    )
                    last_idx = len(text)
                else:
                    next_chunk = text[last_idx:]
                    last_idx = len(text)
                    if not next_chunk:
                        continue  # no chunk, wait for the next update
                    update_msg_id = bot.send_msg(
                        text=next_chunk,
                        send_feedback_buttons=streaming_done and send_feedback_buttons,
                    )
                if streaming_done and not bot.can_update_message:
                    # if we send the buttons, this is the ID we need to record in the db for lookups later when the button is pressed
                    sent_msg_id = update_msg_id
                    # don't show buttons again
                    send_feedback_buttons = False
                if streaming_done:
                    break  # we're done streaming, stop the loop

    # wait for the celery task to finish
    sr.wait_for_celery_result(result)
    # get the final state from db
    state = sr.to_dict()
    bot.recipe_run_state = bot.page_cls.get_run_state(state)
    bot.run_status = state.get(StateKeys.run_status) or ""
    # check for errors
    err_msg = state.get(StateKeys.error_msg)
    if err_msg:
        bot.send_msg(text=ERROR_MSG.format(err_msg))
        return

    text = state.get("output_text") and state.get("output_text")[0]
    audio = state.get("output_audio")
    video = state.get("output_video")
    documents = state.get("output_documents")
    # check for empty response
    if not (text or audio or video or documents or send_feedback_buttons):
        bot.send_msg(text=DEFAULT_RESPONSE)
        return
    # if in-place updates are enabled, update the message, otherwise send the remaining text
    if text and not bot.can_update_message:
        text = text[last_idx:]
    # send the response to the user if there is any remaining
    if text or audio or video or documents or send_feedback_buttons:
        update_msg_id = bot.send_msg(
            text=text or None,
            audio=audio or None,
            video=video or None,
            documents=documents or None,
            send_feedback_buttons=send_feedback_buttons,
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


def build_system_vars(convo: Conversation, user_msg_id: str) -> tuple[dict, dict]:
    from routers.bots_api import MSG_ID_PREFIX

    bi = convo.bot_integration
    if bi.platform == Platform.WEB:
        user_msg_id = user_msg_id.removeprefix(MSG_ID_PREFIX)
    variables = dict(
        platform=Platform(bi.platform).name,
        integration_id=bi.api_integration_id(),
        integration_name=bi.name,
        conversation_id=convo.api_integration_id(),
        user_message_id=user_msg_id,
    )
    match bi.platform:
        case Platform.FACEBOOK:
            variables["user_fb_page_name"] = convo.fb_page_name
            variables["bot_fb_page_name"] = bi.fb_page_name
        case Platform.INSTAGRAM:
            variables["user_ig_username"] = convo.ig_username
            variables["bot_ig_username "] = bi.ig_username
        case Platform.WHATSAPP:
            variables["user_wa_phone_number"] = (
                convo.wa_phone_number and convo.wa_phone_number.as_international
            )
            variables["bot_wa_phone_number"] = (
                bi.wa_phone_number and bi.wa_phone_number.as_international
            )
        case Platform.SLACK:
            variables["slack_user_name"] = convo.slack_user_name
            variables["slack_channel_name"] = convo.slack_channel_name
            variables["slack_team_name"] = bi.slack_team_name
        case Platform.WEB:
            variables["web_user_id"] = convo.web_user_id
        case Platform.TWILIO:
            variables["user_twilio_phone_number"] = (
                convo.twilio_phone_number and convo.twilio_phone_number.as_international
            )
            variables["bot_twilio_phone_number"] = (
                bi.twilio_phone_number and bi.twilio_phone_number.as_international
            )
    variables_schema = {var: {"role": "system"} for var in variables}
    return variables, variables_schema


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
    button = bot.get_interactive_msg_info()
    match button.button_id:
        # handle feedback button press
        case ButtonIds.feedback_thumbs_up | ButtonIds.feedback_thumbs_down:
            context_msg = Message.objects.get(
                platform_msg_id=button.context_msg_id, conversation=bot.convo
            )
            if button.button_id == ButtonIds.feedback_thumbs_up:
                rating = Feedback.Rating.RATING_THUMBS_UP
                # bot.convo.state = ConvoState.ASK_FOR_FEEDBACK_THUMBS_UP
                # response_text = FEEDBACK_THUMBS_UP_MSG
            else:
                rating = Feedback.Rating.RATING_THUMBS_DOWN
                # bot.convo.state = ConvoState.ASK_FOR_FEEDBACK_THUMBS_DOWN
                # response_text = FEEDBACK_THUMBS_DOWN_MSG
            response_text = FEEDBACK_CONFIRMED_MSG.format(bot_name=str(bot.bi.name))
            bot.convo.save()
            # save the feedback
            Feedback.objects.create(message=context_msg, rating=rating)
            # send a confirmation msg + post click buttons
            bot.send_msg(
                text=response_text,
                # buttons=_feedback_post_click_buttons(),
                should_translate=True,
            )
            return True

        # handle skip
        case ButtonIds.action_skip:
            bot.send_msg(text=TAPPED_SKIP_MSG, should_translate=True)
            # reset state
            bot.convo.state = ConvoState.INITIAL
            bot.convo.save()
            return True

        # not sure what button was pressed, ignore
        case _:
            import glom

            # encoded by parse_html
            target, title = None, None
            parts = csv_decode_row(button.button_id)
            if len(parts) >= 3:
                target = parts[1]
                title = parts[-1]
            bot.request_overrides = bot.request_overrides or {}
            glom.assign(
                bot.request_overrides,
                target or "input_prompt",
                title or button.button_title,
            )
            return False


def _handle_location_msg(input_location: dict[str, float]) -> str:
    r = requests.post(
        url="https://maps.googleapis.com/maps/api/geocode/json",
        params={
            "latlng": f"{input_location['latitude']},{input_location['longitude']}",
            "key": settings.GOOGLE_GEOCODING_API_KEY,
        },
    )
    raise_for_status(r)
    data = r.json()

    input_text = f"My present location is: {input_location}\n"
    try:
        formatted_address = [result["formatted_address"] for result in data["results"]]
    except (KeyError, IndexError, TypeError):
        input_text += "Geocoding Response could not be retrieved"
    else:
        input_text += f"Geocoding Response: {formatted_address}"

    return input_text


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
