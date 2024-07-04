from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.twiml.messaging_response import MessagingResponse

from app_users.models import AppUser
from bots.models import Conversation, BotIntegration, SavedRun, PublishedRun, Platform
from daras_ai_v2 import settings
from starlette.background import BackgroundTasks

from furl import furl
from fastapi import APIRouter, Response
from daras_ai_v2.fastapi_tricks import fastapi_request_urlencoded_body
import base64

router = APIRouter()


@router.post("/__/twilio/voice/")
def twilio_voice_call(data: dict = fastapi_request_urlencoded_body):
    """Handle incoming Twilio voice call."""

    # data = {'AccountSid': ['XXXX'], 'ApiVersion': ['2010-04-01'], 'CallSid': ['XXXX'], 'CallStatus': ['ringing'], 'CallToken': ['XXXX'], 'Called': ['XXXX'], 'CalledCity': ['XXXX'], 'CalledCountry': ['XXXX'], 'CalledState': ['XXXX'], 'CalledZip': ['XXXX'], 'Caller': ['XXXX'], 'CallerCity': ['XXXX'], 'CallerCountry': ['XXXX'], 'CallerState': ['XXXX'], 'CallerZip': ['XXXX'], 'Direction': ['inbound'], 'From': ['XXXX'], 'FromCity': ['XXXX'], 'FromCountry': ['XXXX'], 'FromState': ['XXXX'], 'FromZip': ['XXXX'], 'StirVerstat': ['XXXX'], 'To': ['XXXX'], 'ToCity': ['XXXX'], 'ToCountry': ['XXXX'], 'ToState': ['XXXX'], 'ToZip': ['XXXX']}

    account_sid = data["AccountSid"][0]
    phone_number = data["To"][0]

    try:
        bi = BotIntegration.objects.get(
            twilio_account_sid=account_sid, twilio_phone_number=phone_number
        )
    except BotIntegration.DoesNotExist:
        return Response(status_code=404)

    if bi.twilio_use_missed_call:
        resp = VoiceResponse()
        resp.reject()

        # TODO: use start_voice_call to call the user back after a short delay

        return Response(str(resp), headers={"Content-Type": "text/xml"})

    resp = VoiceResponse()

    gather = Gather(
        input="speech",  # also supports dtmf (keypad input) and a combination of both
        timeout=20,  # users get 20 to start speaking
        speechTimeout=3,  # a 3 second pause ends the input
        action=url_for(twilio_voice_call_ask),  # the URL to send the user's question to
        method="POST",
        finish_on_key="0",  # user can press 0 to end the input
        language=bi.twilio_asr_language,
        speech_model="phone_call",  # optimized for phone call audio
        enhanced=True,  # only phone_call model supports enhanced
    )

    # say the initial text/audio while allowing the user to interrupt with their question if they want
    if bi.twilio_initial_text.strip():
        gather.say(bi.twilio_initial_text, voice=bi.twilio_voice)
    if bi.twilio_initial_audio_url.strip():
        gather.play(bi.twilio_initial_audio_url)
    if not bi.twilio_initial_text and not bi.twilio_initial_audio_url:
        gather.say(
            f"Welcome to {bi.name}! Please ask your question and press 0 if the end of your question isn't detected.",
            voice=bi.twilio_voice,
        )

    resp.append(gather)

    # if the user doesn't say anything, we'll ask them to call back in a quieter environment
    resp.say(
        "Sorry, I didn't get that. Please call again in a more quiet environment.",
        voice=bi.twilio_voice,
    )

    return Response(str(resp), headers={"Content-Type": "text/xml"})


@router.post("/__/twilio/voice/listen/{bi_id}/")
def twilio_voice_call_listen(bi_id: int):
    """Listen for a response. Not the initial call, but has just responded to a question."""

    try:
        bi = BotIntegration.objects.get(id=bi_id)
    except BotIntegration.DoesNotExist:
        return Response(status_code=404)

    resp = VoiceResponse()

    resp.gather(
        input="speech",  # also supports dtmf (keypad input) and a combination of both
        timeout=20,  # users get 20 to start speaking
        speechTimeout=3,  # a 3 second pause ends the input
        action=url_for(twilio_voice_call_ask),  # the URL to send the user's question to
        method="POST",
        finish_on_key="0",  # user can press 0 to end the input
        language=bi.twilio_asr_language,
        speech_model="phone_call",  # optimized for phone call audio
        enhanced=True,  # only phone_call model supports enhanced
    )

    return Response(str(resp), headers={"Content-Type": "text/xml"})


@router.post("/__/twilio/voice/ask/")
def twilio_voice_call_ask(
    background_tasks: BackgroundTasks, data: dict = fastapi_request_urlencoded_body
):
    """After the initial call, the user has been asked a question. Handle their question."""
    from daras_ai_v2.bots import msg_handler
    from daras_ai_v2.twilio_bot import TwilioVoice

    # data = {'AccountSid': ['XXXX'], 'ApiVersion': ['2010-04-01'], 'CallSid': ['XXXX'], 'CallStatus': ['in-progress'], 'Called': ['XXXX'], 'CalledCity': ['XXXX'], 'CalledCountry': ['XXXX'], 'CalledState': ['XXXX'], 'CalledZip': ['XXXX'], 'Caller': ['XXXX'], 'CallerCity': ['XXXX'], 'CallerCountry': ['XXXX'], 'CallerState': ['XXXX'], 'CallerZip': ['XXXX'], 'Confidence': ['0.9128386'], 'Direction': ['inbound'], 'From': ['XXXX'], 'FromCity': ['XXXX'], 'FromCountry': ['XXXX'], 'FromState': ['XXXX'], 'FromZip': ['XXXX'], 'Language': ['en-US'], 'SpeechResult': ['Hello.'], 'To': ['XXXX'], 'ToCity': ['XXXX'], 'ToCountry': ['XXXX'], 'ToState': ['XXXX'], 'ToZip': ['XXXX']}

    account_sid = data["AccountSid"][0]
    user_phone_number = data["From"][0]
    phone_number = data["To"][0]
    text = data["SpeechResult"][0]

    try:
        bi = BotIntegration.objects.get(
            twilio_account_sid=account_sid, twilio_phone_number=phone_number
        )
    except BotIntegration.DoesNotExist:
        return Response(status_code=404)

    # start processing the user's question
    queue_name = f"Queue for {bi.name} ({user_phone_number})"
    bot = TwilioVoice(
        incoming_number=user_phone_number,
        queue_name=queue_name,
        text=text,
        audio=None,
        bi=bi,
    )
    background_tasks.add_task(msg_handler, bot)

    # send back waiting audio
    resp = VoiceResponse()
    resp.say("I heard " + text, voice=bi.twilio_voice)

    resp.enqueue(
        name=queue_name,
        wait_url=url_for(twilio_voice_call_wait, bi_id=bi.id),
        wait_url_method="POST",
    )

    return Response(str(resp), headers={"Content-Type": "text/xml"})


@router.post("/__/twilio/voice/wait/{bi_id}/")
def twilio_voice_call_wait(bi_id: int):
    """Play the waiting audio for the user in the queue."""

    try:
        bi = BotIntegration.objects.get(id=bi_id)
    except BotIntegration.DoesNotExist:
        return Response(status_code=404)

    resp = VoiceResponse()

    if bi.twilio_waiting_audio_url:
        resp.play(bi.twilio_waiting_audio_url)
    else:
        resp.play("http://com.twilio.sounds.music.s3.amazonaws.com/ClockworkWaltz.mp3")
        resp.play("http://com.twilio.sounds.music.s3.amazonaws.com/BusyStrings.mp3")
        resp.play(
            "http://com.twilio.sounds.music.s3.amazonaws.com/oldDog_-_endless_goodbye_%28instr.%29.mp3"
        )
        resp.play(
            "http://com.twilio.sounds.music.s3.amazonaws.com/Mellotroniac_-_Flight_Of_Young_Hearts_Flute.mp3"
        )
        resp.play(
            "http://com.twilio.sounds.music.s3.amazonaws.com/MARKOVICHAMP-Borghestral.mp3"
        )

    return Response(str(resp), headers={"Content-Type": "text/xml"})


def twilio_voice_call_respond(
    text: str | None,
    audio_url: str | None,
    queue_name: str,
    user_phone_number: str,
    bi: BotIntegration,
):
    """Respond to the user in the queue with the given text and audio URL."""

    text = text
    audio_url = audio_url
    text = base64.b64encode(text.encode()).decode() if text else "N"
    audio_url = base64.b64encode(audio_url.encode()).decode() if audio_url else "N"

    queue_sid = None
    client = Client(bi.twilio_account_sid, bi.twilio_auth_token)
    for queue in client.queues.list():
        if queue.friendly_name == queue_name:
            queue_sid = queue.sid
            break
    assert queue_sid, "Queue not found"

    client.queues(queue_sid).members("Front").update(
        url=url_for(
            twilio_voice_call_response, bi_id=bi.id, text=text, audio_url=audio_url
        ),
        method="POST",
    )

    return queue_sid


@router.post("/__/twilio/voice/response/{bi_id}/{text}/{audio_url}/")
def twilio_voice_call_response(
    bi_id: int, text: str, audio_url: str, data: dict = fastapi_request_urlencoded_body
):
    """Response is ready, user has been dequeued, send the response."""

    print("Twilio voice response", data)

    text = base64.b64decode(text).decode() if text != "N" else ""
    audio_url = base64.b64decode(audio_url).decode() if audio_url != "N" else ""

    resp = VoiceResponse()

    if text:
        resp.say(text)
    if audio_url:
        resp.play(audio_url)

    resp.redirect(url_for(twilio_voice_call_listen, bi_id=bi_id))

    return Response(str(resp), headers={"Content-Type": "text/xml"})


# used for debugging, can be removed
@router.post("/__/twilio/voice/status/")
def twilio_voice_call_status(data: dict = fastapi_request_urlencoded_body):
    """Handle incoming Twilio voice call status update."""

    print("Twilio status update", data)

    return Response(status_code=204)


@router.post("/__/twilio/voice/error/")
def twilio_voice_call_error():
    """If an unhandled error occurs in the voice call webhook, return a generic error message."""

    resp = VoiceResponse()
    resp.say(
        "Sorry. This number has been incorrectly configured. Contact the bot integration owner or try again later."
    )

    return Response(str(resp), headers={"Content-Type": "text/xml"})


@router.post("/__/twilio/sms/")
def twilio_sms(data: dict = fastapi_request_urlencoded_body):
    """Handle incoming Twilio SMS."""
    print("Twilio SMS", data)

    resp = MessagingResponse()
    resp.message("Thank you for your message!")

    return Response(str(resp), headers={"Content-Type": "text/xml"})


@router.post("/__/twilio/sms/error/")
def twilio_sms_error():
    """If an unhandled error occurs in the SMS webhook, return a generic error message."""

    resp = MessagingResponse()
    resp.message(
        "Sorry. This number has been incorrectly configured. Contact the bot integration owner or try again later."
    )

    return Response(str(resp), headers={"Content-Type": "text/xml"})


def start_voice_call(convo: Conversation, text: str | None, audio_url: str | None):
    """Start a new voice call saying the given text and audio URL. Useful for notifications."""

    assert (
        convo.twilio_phone_number
    ), "This is not a Twilio conversation, it has no phone number."

    voice = convo.bot_integration.twilio_voice

    account_sid = convo.bot_integration.twilio_account_sid
    auth_token = convo.bot_integration.twilio_auth_token
    client = Client(account_sid, auth_token)

    resp = VoiceResponse()
    if text:
        resp.say(text, voice=voice)
    if audio_url:
        resp.play(audio_url)

    call = client.calls.create(
        twiml=str(resp),
        to=convo.twilio_phone_number,
        from_=convo.bot_integration.twilio_phone_number,
    )

    return call


def send_sms_message(convo: Conversation, text: str, media_url: str | None = None):
    """Send an SMS message to the given conversation."""

    assert (
        convo.twilio_phone_number
    ), "This is not a Twilio conversation, it has no phone number."

    account_sid = convo.bot_integration.twilio_account_sid
    auth_token = convo.bot_integration.twilio_auth_token
    client = Client(account_sid, auth_token)

    message = client.messages.create(
        body=text,
        media_url=media_url,
        from_=convo.bot_integration.twilio_phone_number,
        to=convo.twilio_phone_number,
    )

    return message


def url_for(fx, **kwargs):
    """Get the URL for the given Twilio endpoint."""

    return (
        furl(
            settings.APP_BASE_URL,
        )
        / router.url_path_for(fx.__name__, **kwargs)
    ).tostr()


def twilio_connect(
    current_run: SavedRun,
    published_run: PublishedRun,
    twilio_account_sid: str,
    twilio_auth_token: str,
    twilio_phone_number: str,
    twilio_phone_number_sid: str,
    billing_user: AppUser,
) -> BotIntegration:
    """Connect a new bot integration to Twilio and return it. This will also setup the necessary webhooks for voice calls and SMS messages"""

    # setup webhooks so we can receive voice calls and SMS messages
    client = Client(twilio_account_sid, twilio_auth_token)
    client.incoming_phone_numbers(twilio_phone_number_sid).update(
        sms_fallback_method="POST",
        sms_fallback_url=url_for(twilio_sms_error),
        sms_method="POST",
        sms_url=url_for(twilio_sms),
        status_callback_method="POST",
        status_callback=url_for(twilio_voice_call_status),
        voice_fallback_method="POST",
        voice_fallback_url=url_for(twilio_voice_call_error),
        voice_method="POST",
        voice_url=url_for(twilio_voice_call),
    )

    # create bot integration
    return BotIntegration.objects.create(
        name=published_run.title,
        billing_account_uid=billing_user.uid,
        platform=Platform.TWILIO,
        streaming_enabled=False,
        saved_run=current_run,
        published_run=published_run,
        by_line=billing_user.display_name,
        descripton=published_run.notes,
        photo_url=billing_user.photo_url,
        website_url=billing_user.website_url,
        user_language=current_run.state.get("user_language") or "en",
        twilio_account_sid=twilio_account_sid,
        twilio_auth_token=twilio_auth_token,
        twilio_phone_number=twilio_phone_number,
        twilio_phone_number_sid=twilio_phone_number_sid,
    )
