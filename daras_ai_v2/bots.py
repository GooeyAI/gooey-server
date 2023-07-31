import mimetypes
import typing
import traceback

from sentry_sdk import capture_exception
from fastapi import HTTPException, Request
from furl import furl

from daras_ai_v2.base import BasePage
from daras_ai_v2.all_pages import Workflow
from daras_ai_v2.asr import AsrModels, run_google_translate
from daras_ai_v2.language_model import CHATML_ROLE_USER, CHATML_ROLE_ASSISSTANT
from gooeysite.bg_db_conn import db_middleware

from app_users.models import AppUser
from bots.models import (
    BotIntegration,
    Platform,
    Message,
    Conversation,
    Feedback,
    SavedRun,
    ConvoState,
)


async def request_json(request: Request):
    return await request.json()


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
    convo: Conversation

    def send_msg(
        self,
        *,
        text: str = None,
        audio: str = None,
        video: str = None,
        buttons: list = None,
        should_translate: bool = False,
    ) -> str | None:
        raise NotImplementedError

    def mark_read(self):
        raise NotImplementedError

    def get_input_text(self) -> str | None:
        raise NotImplementedError

    def get_input_audio(self) -> str | None:
        raise NotImplementedError

    def get_input_video(self) -> str | None:
        raise NotImplementedError

    def nice_filename(self, mime_type: str) -> str:
        ext = mimetypes.guess_extension(mime_type) or ""
        return f"{self.platform}_{self.input_type}_from_{self.user_id}_to_{self.bot_id}{ext}"

    def _unpack_bot_integration(self, bi: BotIntegration):
        self.page_cls = Workflow(bi.saved_run.workflow).page_cls
        self.query_params = self.page_cls.clean_query_params(
            example_id=bi.saved_run.example_id,
            run_id=bi.saved_run.run_id,
            uid=bi.saved_run.uid,
        )
        self.billing_account_uid = bi.billing_account_uid
        self.language = bi.user_language
        self.show_feedback_buttons = bi.show_feedback_buttons


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
`{0!r}`

⚠️ Sorry, I ran into an error while processing your request. Please try again, or type "Reset" to start over.
""".strip()

FEEDBACK_THUMBS_UP_MSG = "🎉 What did you like about my response?"
FEEDBACK_THUMBS_DOWN_MSG = "🤔 What was the issue with the response? How could it be improved? Please send me an voice note or text me."
FEEDBACK_CONFIRMED_MSG = (
    "🙏 Thanks! Your feedback helps us make {bot_name} better. How else can I help you?"
)

TAPPED_SKIP_MSG = "🌱 Alright. What else can I help you with?"


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
    if not bot.page_cls:
        bot.send_msg(text=PAGE_NOT_CONNECTED_ERROR)
        return
    # mark message as read
    bot.mark_read()
    # get the attached billing account
    billing_account_user = AppUser.objects.get_or_create_from_uid(
        bot.billing_account_uid
    )[0]
    # get the user's input
    match bot.input_type:
        # handle button press
        case "interactive":
            _handle_interactive_msg(bot)
            return
        case "audio":
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
    last_feedback.text_english = " ".join(run_google_translate([input_text], "en"))
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
    input_text: str,
    speech_run: str | None,
):
    try:
        # # mock testing
        # msgs_to_save, response_audio, response_text, response_video = _echo(
        #     bot, input_text
        # )
        # make API call to gooey bots to get the response
        response_text, response_audio, response_video, msgs_to_save = _process_msg(
            page_cls=bot.page_cls,
            api_user=billing_account_user,
            query_params=bot.query_params,
            convo=bot.convo,
            input_text=input_text,
            user_language=bot.language,
            speech_run=speech_run,
        )
    except HTTPException as e:
        traceback.print_exc()
        capture_exception(e)
        # send error msg as repsonse
        bot.send_msg(text=ERROR_MSG.format(e))
        return
    # this really shouldn't happen, but just in case it does, we should have a nice message
    response_text = response_text or DEFAULT_RESPONSE
    # send the response to the user
    msg_id = bot.send_msg(
        text=response_text,
        audio=response_audio,
        video=response_video,
        buttons=_feedback_start_buttons() if bot.show_feedback_buttons else None,
    )
    if not msgs_to_save:
        return
    # save the whatsapp message id for the sent message
    if bot.platform == Platform.WHATSAPP and msg_id:
        msgs_to_save[-1].wa_msg_id = msg_id
    # save the messages
    for msg in msgs_to_save:
        msg.save()


def _handle_interactive_msg(bot: BotInterface):
    try:
        button_id = bot.input_message["interactive"]["button_reply"]["id"]
        context_msg_id = bot.input_message["context"]["id"]
    except (KeyError,) as e:
        bot.send_msg(text=ERROR_MSG.format(e))
        return
    match button_id:
        # handle feedback button press
        case ButtonIds.feedback_thumbs_up | ButtonIds.feedback_thumbs_down:
            try:
                context_msg = Message.objects.get(wa_msg_id=context_msg_id)
            except Message.DoesNotExist as e:
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


def _handle_audio_msg(billing_account_user, bot):
    from recipes.asr import AsrPage
    from routers.api import call_api

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
        case _:
            selected_model = AsrModels.whisper_large_v2.name
    result = call_api(
        page_cls=AsrPage,
        user=billing_account_user,
        request_body={
            "documents": [bot.get_input_audio()],
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


def _feedback_post_click_buttons():
    """
    Buttons to show after the user has clicked on a feedback button
    """
    return [
        {
            "type": "reply",
            "reply": {"id": ButtonIds.action_skip, "title": "🔀 Skip"},
        },
    ]


def _feedback_start_buttons():
    """
    Buttons to show for collecting feedback after the bot has sent a response
    """
    return [
        {
            "type": "reply",
            "reply": {"id": ButtonIds.feedback_thumbs_up, "title": "👍🏾"},
        },
        {
            "type": "reply",
            "reply": {"id": ButtonIds.feedback_thumbs_down, "title": "👎🏽"},
        },
    ]


def _process_msg(
    *,
    page_cls,
    api_user: AppUser,
    query_params: dict,
    convo: Conversation,
    input_text: str,
    user_language: str,
    speech_run: str | None,
) -> tuple[str, str | None, str | None, list[Message]]:
    from routers.api import call_api

    # get latest messages for context (upto 100)
    saved_msgs = list(
        reversed(
            convo.messages.order_by("-created_at").values("role", "content")[:100],
        ),
    )

    # # mock testing
    # result = _mock_api_output(input_text)

    # call the api with provided input
    result = call_api(
        page_cls=page_cls,
        user=api_user,
        request_body={
            "input_prompt": input_text,
            "messages": saved_msgs,
            "user_language": user_language,
        },
        query_params=query_params,
    )

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
            saved_run=SavedRun.objects.get_or_create(
                workflow=Workflow.ASR, **furl(speech_run).query.params
            )[0]
            if speech_run
            else None,
        ),
        Message(
            conversation=convo,
            role=CHATML_ROLE_ASSISSTANT,
            content=raw_output_text,
            display_content=output_text,
            saved_run=SavedRun.objects.get_or_create(
                workflow=Workflow.VIDEOBOTS, **furl(result.get("url", "")).query.params
            )[0],
        ),
    ]
    return response_text, response_audio, response_video, msgs_to_save
