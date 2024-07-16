import random
import traceback
from time import sleep

from fastapi import APIRouter, Response
from loguru import logger
from sentry_sdk import capture_exception
from starlette.background import BackgroundTasks
from twilio.twiml import TwiML
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse, Gather

from app_users.models import AppUser
from bots.models import Conversation, BotIntegration
from daras_ai_v2.bots import msg_handler
from daras_ai_v2.fastapi_tricks import (
    fastapi_request_urlencoded_body,
    get_api_route_url,
)
from daras_ai_v2.twilio_bot import TwilioVoice
from gooeysite.bg_db_conn import get_celery_result_db_safe
from recipes.TextToSpeech import TextToSpeechPage

DEFAULT_INITIAL_TEXT = "Welcome to {bot_name}! Please ask your question and press 0 if the end of your question isn't detected."
DEFAULT_WAITING_AUDIO_URLS = [
    "http://com.twilio.sounds.music.s3.amazonaws.com/ClockworkWaltz.mp3",
    "http://com.twilio.sounds.music.s3.amazonaws.com/BusyStrings.mp3",
    "http://com.twilio.sounds.music.s3.amazonaws.com/oldDog_-_endless_goodbye_%28instr.%29.mp3",
    "http://com.twilio.sounds.music.s3.amazonaws.com/Mellotroniac_-_Flight_Of_Young_Hearts_Flute.mp3",
    "http://com.twilio.sounds.music.s3.amazonaws.com/MARKOVICHAMP-Borghestral.mp3",
]
DEFAULT_VOICE_NAME = "Google.en-US-Wavenet-F"
DEFAULT_ASR_LANGUAGE = "en-US"

SILENCE_RESPONSE = (
    "Sorry, I didn't get that. Please call again in a more quiet environment."
)

router = APIRouter()


@router.post("/__/twilio/voice/")
def twilio_voice_call(
    background_tasks: BackgroundTasks, data: dict = fastapi_request_urlencoded_body
):
    """Handle incoming Twilio voice call."""

    bot = TwilioVoice.from_data(data)
    bi = bot.bi

    text = bi.twilio_initial_text.strip()
    audio_url = bi.twilio_initial_audio_url.strip()
    if not text and not audio_url:
        text = DEFAULT_INITIAL_TEXT.format(bot_name=bi.name)

    resp = create_voice_call_response(
        bot, text=text, audio_url=audio_url, should_translate=True
    )

    if bi.twilio_use_missed_call:
        # if not data.get("StirVerstat"):
        background_tasks.add_task(start_voice_call_session, bot=bot, resp=resp)
        sleep(1)
        resp = VoiceResponse()
        resp.reject()

    return twiml_response(resp)


def start_voice_call_session(*, bot: TwilioVoice, resp: VoiceResponse):
    client = bot.bi.get_twilio_client()
    return client.calls.create(twiml=str(resp), from_=bot.bot_id, to=bot.user_id)


@router.post("/__/twilio/voice/response/")
def twilio_voice_call_response(
    background_tasks: BackgroundTasks,
    convo_id: str,
    text: str = None,
    audio_url: str = None,
    data: dict = fastapi_request_urlencoded_body,
):
    """Response is ready, user has been dequeued, send the response and ask for the next one."""
    logger.debug(data)
    try:
        convo = Conversation.objects.get(id=int(convo_id))
    except Conversation.DoesNotExist:
        return Response(status_code=404)
    bot = TwilioVoice(convo=convo)
    resp = create_voice_call_response(bot, text=text, audio_url=audio_url)
    background_tasks.add_task(delete_queue, bi=bot.bi, queue_sid=data["QueueSid"][0])
    return twiml_response(resp)


def delete_queue(bi: BotIntegration, queue_sid: str):
    bi.get_twilio_client().queues(queue_sid).delete()


def create_voice_call_response(
    bot: TwilioVoice, *, text: str, audio_url: str, should_translate: bool = False
) -> VoiceResponse:
    resp = VoiceResponse()

    # the URL to send the user's question to
    action = get_api_route_url(twilio_voice_call_asked)

    if bot.use_gooey_asr:
        # record does not support nesting, so we can't support interrupting the response with the next question
        if audio_url:
            resp.play(audio_url)
        elif text:
            resp_say_or_tts_play(bot, resp, text, should_translate=should_translate)

        # try recording 3 times to give the user a chance to start speaking
        for _ in range(3):
            resp.record(
                action=action,
                method="POST",
                timeout=3,
                finish_on_key="0",
                play_beep=False,
            )
    else:
        gather = Gather(
            input="speech",  # also supports dtmf (keypad input) and a combination of both
            timeout=20,  # users get 20 to start speaking
            speechTimeout=3,  # a 3 second pause ends the input
            action=action,
            method="POST",
            finish_on_key="0",  # user can press 0 to end the input
            language=bot.bi.twilio_asr_language or DEFAULT_ASR_LANGUAGE,
            speech_model="phone_call",  # optimized for phone call audio
            enhanced=True,  # only phone_call model supports enhanced
        )

        # by attaching to gather, we allow the user to interrupt with the next question while the response is playing
        if audio_url:
            gather.play(audio_url)
        elif text:
            resp_say_or_tts_play(bot, gather, text, should_translate=should_translate)

        resp.append(gather)

    # if the user doesn't say anything, we'll ask them to call back in a quieter environment
    resp_say_or_tts_play(bot, resp, SILENCE_RESPONSE, should_translate=True)

    return resp


@router.post("/__/twilio/voice/asked/")
def twilio_voice_call_asked(
    background_tasks: BackgroundTasks, data: dict = fastapi_request_urlencoded_body
):
    """After the initial call, the user has asked a question via Twilio/Gooey ASR. Handle their question."""

    bot = TwilioVoice.from_data(data)
    background_tasks.add_task(msg_handler, bot)

    resp = VoiceResponse()
    if bot.input_type == "text":
        resp_say_or_tts_play(
            bot, resp, "I heard " + bot.get_input_text(), should_translate=True
        )
    # send back waiting audio, and wait for the msg_handler to send the response
    resp.enqueue(
        name=bot.twilio_queue.friendly_name,
        wait_url=get_api_route_url(
            twilio_voice_call_wait,
            query_params=dict(audio_url=bot.bi.twilio_waiting_audio_url),
        ),
    )
    return twiml_response(resp)


@router.post("/__/twilio/voice/wait/")
def twilio_voice_call_wait(audio_url: str = None):
    """Play the waiting audio for the user in the queue."""
    resp = VoiceResponse()
    if audio_url:
        audio_urls = [audio_url]
    else:
        random.shuffle(DEFAULT_WAITING_AUDIO_URLS)
        audio_urls = DEFAULT_WAITING_AUDIO_URLS
    for url in audio_urls:
        resp.play(url)
    return twiml_response(resp)


# uncomment for debugging:
@router.post("/__/twilio/voice/status/")
def twilio_voice_call_status(data: dict = fastapi_request_urlencoded_body):
    """Handle incoming Twilio voice call status update."""

    print("Twilio status update", data)

    return Response(status_code=204)


def resp_say_or_tts_play(
    bot: TwilioVoice,
    resp: VoiceResponse | Gather,
    text: str,
    *,
    should_translate: bool = False,
):
    """Say the given text using the bot integration's voice. If the bot integration is set to use Gooey TTS, use that instead."""

    if should_translate:
        text = bot.translate_response(text)

    if bot.use_gooey_tts:
        try:
            # submit the TTS request
            tts_state = TextToSpeechPage.RequestModel.parse_obj(
                {**bot.saved_run.state, "text_prompt": text}
            ).dict()
            result, sr = TextToSpeechPage.get_root_published_run().submit_api_call(
                current_user=AppUser.objects.get(uid=bot.billing_account_uid),
                request_body=tts_state,
            )
            # wait for the TTS to finish
            get_celery_result_db_safe(result)
            sr.refresh_from_db()
            # check for errors
            if sr.error_msg:
                raise RuntimeError(sr.error_msg)
            # play the audio
            resp.play(sr.state["audio_url"])
        except Exception as e:
            traceback.print_exc()
            capture_exception(e)
            # continue with the text if the TTS fails
        else:
            return

    resp.say(text, voice=bot.bi.twilio_tts_voice or DEFAULT_VOICE_NAME)


@router.post("/__/twilio/voice/error/")
def twilio_voice_call_error():
    """If an unhandled error occurs in the voice call webhook, return a generic error message."""

    resp = VoiceResponse()
    resp.say(
        "Sorry. This number has been incorrectly configured. Contact the bot integration owner or try again later."
    )

    return twiml_response(resp)


@router.post("/__/twilio/sms/")
def twilio_sms(
    background_tasks: BackgroundTasks, data: dict = fastapi_request_urlencoded_body
):
    """Handle incoming Twilio SMS."""
    from daras_ai_v2.twilio_bot import TwilioSMS
    from daras_ai_v2.bots import msg_handler

    bot = TwilioSMS(data)
    background_tasks.add_task(msg_handler, bot)

    resp = MessagingResponse()

    if bot.bi.twilio_waiting_text.strip():
        text = bot.bi.twilio_waiting_text

    else:
        text = "Please wait while we process your request."
    resp.message(bot.translate_response(text))

    return twiml_response(resp)


@router.post("/__/twilio/sms/error/")
def twilio_sms_error():
    """If an unhandled error occurs in the SMS webhook, return a generic error message."""

    resp = MessagingResponse()
    resp.message(
        "Sorry. This number has been incorrectly configured. Contact the bot integration owner or try again later."
    )

    return twiml_response(resp)


def twiml_response(twiml: TwiML) -> Response:
    xml = str(twiml)
    logger.debug(xml)
    return Response(xml, headers={"Content-Type": "text/xml"})
