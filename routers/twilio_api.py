from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.twiml.messaging_response import MessagingResponse

from app_users.models import AppUser
from bots.models import Conversation, BotIntegration, SavedRun, PublishedRun, Platform
from phonenumber_field.phonenumber import PhoneNumber

from fastapi import APIRouter, Response
from starlette.background import BackgroundTasks
from daras_ai_v2.fastapi_tricks import fastapi_request_urlencoded_body, get_route_url
import base64
from sentry_sdk import capture_exception

router = APIRouter()


def say(resp: VoiceResponse, text: str, bi: BotIntegration):
    """Say the given text using the bot integration's voice. If the bot integration is set to use Gooey TTS, use that instead."""

    if bi.twilio_default_to_gooey_tts and bi.get_active_saved_run():
        from recipes.TextToSpeech import TextToSpeechPage
        from routers.api import submit_api_call
        from gooeysite.bg_db_conn import get_celery_result_db_safe

        try:
            tts_state = TextToSpeechPage.RequestModel.parse_obj(
                {**bi.get_active_saved_run().state, "text_prompt": text}
            ).dict()
            page, result, run_id, uid = submit_api_call(
                page_cls=TextToSpeechPage,
                user=AppUser.objects.get(uid=bi.billing_account_uid),
                request_body=tts_state,
                query_params={},
            )
            get_celery_result_db_safe(result)
            # get the final state from db
            sr = page.run_doc_sr(run_id, uid)
            state = sr.to_dict()
            resp.play(state["audio_url"])
        except Exception as e:
            resp.say(text, voice=bi.twilio_voice)
            capture_exception(e)
    else:
        resp.say(text, voice=bi.twilio_voice)


@router.post("/__/twilio/voice/")
def twilio_voice_call(
    background_tasks: BackgroundTasks, data: dict = fastapi_request_urlencoded_body
):
    """Handle incoming Twilio voice call."""

    # data = {'AccountSid': ['XXXX'], 'ApiVersion': ['2010-04-01'], 'CallSid': ['XXXX'], 'CallStatus': ['ringing'], 'CallToken': ['XXXX'], 'Called': ['XXXX'], 'CalledCity': ['XXXX'], 'CalledCountry': ['XXXX'], 'CalledState': ['XXXX'], 'CalledZip': ['XXXX'], 'Caller': ['XXXX'], 'CallerCity': ['XXXX'], 'CallerCountry': ['XXXX'], 'CallerState': ['XXXX'], 'CallerZip': ['XXXX'], 'Direction': ['inbound'], 'From': ['XXXX'], 'FromCity': ['XXXX'], 'FromCountry': ['XXXX'], 'FromState': ['XXXX'], 'FromZip': ['XXXX'], 'StirVerstat': ['XXXX'], 'To': ['XXXX'], 'ToCity': ['XXXX'], 'ToCountry': ['XXXX'], 'ToState': ['XXXX'], 'ToZip': ['XXXX']}

    account_sid = data["AccountSid"][0]
    phone_number = data["To"][0]
    user_phone_number = data["From"][0]

    try:
        bi = BotIntegration.objects.get(
            twilio_account_sid=account_sid,
            twilio_phone_number=PhoneNumber.from_string(phone_number),
        )
    except BotIntegration.DoesNotExist as e:
        capture_exception(e)
        return Response(status_code=404)

    text = bi.twilio_initial_text.strip()
    audio_url = bi.twilio_initial_audio_url.strip()
    if not text and not audio_url:
        text = bi.translate(
            f"Welcome to {bi.name}! Please ask your question and press 0 if the end of your question isn't detected.",
        )

    if bi.twilio_use_missed_call:
        resp = VoiceResponse()
        resp.reject()

        background_tasks.add_task(
            start_voice_call_session, text, audio_url, bi, user_phone_number
        )

        return Response(str(resp), headers={"Content-Type": "text/xml"})

    text = base64.b64encode(text.encode()).decode() if text else "N"
    audio_url = base64.b64encode(audio_url.encode()).decode() if audio_url else "N"

    resp = VoiceResponse()
    resp.redirect(
        get_route_url(
            twilio_voice_call_response,
            dict(bi_id=bi.id, text=text, audio_url=audio_url),
        )
    )

    return Response(str(resp), headers={"Content-Type": "text/xml"})


@router.post("/__/twilio/voice/asked/")
def twilio_voice_call_asked(
    background_tasks: BackgroundTasks, data: dict = fastapi_request_urlencoded_body
):
    """After the initial call, the user has asked a question via Twilio ASR. Handle their question."""
    from daras_ai_v2.bots import msg_handler
    from daras_ai_v2.twilio_bot import TwilioVoice

    # data = {'AccountSid': ['XXXX'], 'ApiVersion': ['2010-04-01'], 'CallSid': ['XXXX'], 'CallStatus': ['in-progress'], 'Called': ['XXXX'], 'CalledCity': ['XXXX'], 'CalledCountry': ['XXXX'], 'CalledState': ['XXXX'], 'CalledZip': ['XXXX'], 'Caller': ['XXXX'], 'CallerCity': ['XXXX'], 'CallerCountry': ['XXXX'], 'CallerState': ['XXXX'], 'CallerZip': ['XXXX'], 'Confidence': ['0.9128386'], 'Direction': ['inbound'], 'From': ['XXXX'], 'FromCity': ['XXXX'], 'FromCountry': ['XXXX'], 'FromState': ['XXXX'], 'FromZip': ['XXXX'], 'Language': ['en-US'], 'SpeechResult': ['Hello.'], 'To': ['XXXX'], 'ToCity': ['XXXX'], 'ToCountry': ['XXXX'], 'ToState': ['XXXX'], 'ToZip': ['XXXX']}

    account_sid = data["AccountSid"][0]
    user_phone_number = data["From"][0]
    phone_number = data["To"][0]
    text = data["SpeechResult"][0]
    call_sid = data["CallSid"][0]

    try:
        bi = BotIntegration.objects.get(
            twilio_account_sid=account_sid, twilio_phone_number=phone_number
        )
    except BotIntegration.DoesNotExist as e:
        capture_exception(e)
        return Response(status_code=404)

    # start processing the user's question
    queue_name = f"{bi.id}-{user_phone_number}"
    bot = TwilioVoice(
        incoming_number=user_phone_number,
        queue_name=queue_name,
        call_sid=call_sid,
        text=text,
        audio=None,
        bi=bi,
    )

    background_tasks.add_task(msg_handler, bot)

    # send back waiting audio
    resp = VoiceResponse()
    say(resp, bot.translate("I heard ") + text, bi)

    resp.enqueue(
        name=queue_name,
        wait_url=get_route_url(twilio_voice_call_wait, dict(bi_id=bi.id)),
        wait_url_method="POST",
    )

    return Response(str(resp), headers={"Content-Type": "text/xml"})


@router.post("/__/twilio/voice/asked_audio/")
def twilio_voice_call_asked_audio(
    background_tasks: BackgroundTasks, data: dict = fastapi_request_urlencoded_body
):
    """After the initial call, the user has asked a question via Gooey ASR. Handle their question."""
    from daras_ai_v2.bots import msg_handler
    from daras_ai_v2.twilio_bot import TwilioVoice

    # data: {'AccountSid': ['XXXX'], 'ApiVersion': ['2010-04-01'], 'CallSid': ['XXXX'], 'CallStatus': ['in-progress'], 'Called': ['XXXX'], 'CalledCity': ['XXXX'], 'CalledCountry': ['XXXX'], 'CalledState': ['XXXX'], 'CalledZip': ['XXXX'], 'Caller': ['XXXX'], 'CallerCity': ['XXXX'], 'CallerCountry': ['XXXX'], 'CallerState': ['XXXX'], 'CallerZip': ['XXXX'], 'Direction': ['inbound'], 'From': ['XXXX'], 'FromCity': ['XXXX'], 'FromCountry': ['XXXX'], 'FromState': ['XXXX'], 'FromZip': ['XXXX'], 'RecordingDuration': ['XXXX'], 'RecordingSid': ['XXXX'], 'RecordingUrl': ['https://api.twilio.com/2010-04-01/Accounts/AC5bac377df5bf25292fe863b9ddb2db2e/Recordings/RE0a6ed1afa9efaf42eb93c407b89619dd'], 'To': ['XXXX'], 'ToCity': ['XXXX'], 'ToCountry': ['XXXX'], 'ToState': ['XXXX'], 'ToZip': ['XXXX']}

    account_sid = data["AccountSid"][0]
    user_phone_number = data["From"][0]
    phone_number = data["To"][0]
    audio_url = data["RecordingUrl"][0]  # wav file
    call_sid = data["CallSid"][0]

    try:
        bi = BotIntegration.objects.get(
            twilio_account_sid=account_sid, twilio_phone_number=phone_number
        )
    except BotIntegration.DoesNotExist as e:
        capture_exception(e)
        return Response(status_code=404)

    # start processing the user's question
    queue_name = f"{bi.id}-{user_phone_number}"
    bot = TwilioVoice(
        incoming_number=user_phone_number,
        queue_name=queue_name,
        call_sid=call_sid,
        text=None,
        audio=audio_url,
        bi=bi,
    )

    background_tasks.add_task(msg_handler, bot)

    # send back waiting audio
    resp = VoiceResponse()
    resp.enqueue(
        name=queue_name,
        wait_url=get_route_url(twilio_voice_call_wait, dict(bi_id=bi.id)),
        wait_url_method="POST",
    )

    return Response(str(resp), headers={"Content-Type": "text/xml"})


@router.post("/__/twilio/voice/wait/{bi_id}/")
def twilio_voice_call_wait(bi_id: int):
    """Play the waiting audio for the user in the queue."""

    try:
        bi = BotIntegration.objects.get(id=bi_id)
    except BotIntegration.DoesNotExist as e:
        capture_exception(e)
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


@router.post("/__/twilio/voice/response/{bi_id}/{text}/{audio_url}/")
def twilio_voice_call_response(bi_id: int, text: str, audio_url: str):
    """Response is ready, user has been dequeued, send the response and ask for the next one."""

    text = base64.b64decode(text).decode() if text != "N" else ""
    audio_url = base64.b64decode(audio_url).decode() if audio_url != "N" else ""

    try:
        bi = BotIntegration.objects.get(id=bi_id)
    except BotIntegration.DoesNotExist as e:
        capture_exception(e)
        return Response(status_code=404)

    resp = VoiceResponse()

    if bi.twilio_default_to_gooey_asr:
        # record does not support nesting, so we can't support interrupting the response with the next question
        if text:
            say(resp, text, bi)
        if audio_url:
            resp.play(audio_url)

        # try recording 3 times to give the user a chance to start speaking
        for _ in range(3):
            resp.record(
                action=get_route_url(twilio_voice_call_asked_audio),
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
            action=get_route_url(
                twilio_voice_call_asked
            ),  # the URL to send the user's question to
            method="POST",
            finish_on_key="0",  # user can press 0 to end the input
            language=bi.twilio_asr_language,
            speech_model="phone_call",  # optimized for phone call audio
            enhanced=True,  # only phone_call model supports enhanced
        )

        # by attaching to gather, we allow the user to interrupt with the next question while the response is playing
        if text:
            gather.say(text, voice=bi.twilio_voice)
        if audio_url:
            gather.play(audio_url)

        resp.append(gather)

    # if the user doesn't say anything, we'll ask them to call back in a quieter environment
    say(
        resp,
        bi.translate(
            "Sorry, I didn't get that. Please call again in a more quiet environment."
        ),
        bi,
    )

    return Response(str(resp), headers={"Content-Type": "text/xml"})


# uncomment for debugging:
# @router.post("/__/twilio/voice/status/")
# def twilio_voice_call_status(data: dict = fastapi_request_urlencoded_body):
#     """Handle incoming Twilio voice call status update."""

#     print("Twilio status update", data)

#     return Response(status_code=204)


@router.post("/__/twilio/voice/error/")
def twilio_voice_call_error():
    """If an unhandled error occurs in the voice call webhook, return a generic error message."""

    resp = VoiceResponse()
    resp.say(
        "Sorry. This number has been incorrectly configured. Contact the bot integration owner or try again later."
    )

    return Response(str(resp), headers={"Content-Type": "text/xml"})


@router.post("/__/twilio/sms/")
def twilio_sms(
    background_tasks: BackgroundTasks, data: dict = fastapi_request_urlencoded_body
):
    """Handle incoming Twilio SMS."""
    from daras_ai_v2.twilio_bot import TwilioSMS
    from daras_ai_v2.bots import msg_handler

    phone_number = data["To"][0]
    user_phone_number = data["From"][0]

    try:
        bi = BotIntegration.objects.get(
            twilio_phone_number=PhoneNumber.from_string(phone_number)
        )
    except BotIntegration.DoesNotExist as e:
        capture_exception(e)
        return Response(status_code=404)

    convo, created = Conversation.objects.get_or_create(
        bot_integration=bi,
        twilio_phone_number=PhoneNumber.from_string(user_phone_number),
    )
    bot = TwilioSMS(
        sid=data["MessageSid"][0],
        convo=convo,
        text=data["Body"][0],
        bi=bi,
    )
    background_tasks.add_task(msg_handler, bot)

    resp = MessagingResponse()

    if created and bi.twilio_initial_text.strip():
        resp.message(bi.twilio_initial_text)

    if bi.twilio_waiting_text.strip():
        resp.message(bi.twilio_waiting_text)
    else:
        resp.message(bot.translate("Please wait while we process your request."))

    return Response(str(resp), headers={"Content-Type": "text/xml"})


@router.post("/__/twilio/sms/error/")
def twilio_sms_error():
    """If an unhandled error occurs in the SMS webhook, return a generic error message."""

    resp = MessagingResponse()
    resp.message(
        "Sorry. This number has been incorrectly configured. Contact the bot integration owner or try again later."
    )

    return Response(str(resp), headers={"Content-Type": "text/xml"})


def start_voice_call_session(
    text: str, audio_url: str, bi: BotIntegration, user_phone_number: str
):
    client = Client(bi.twilio_account_sid, bi.twilio_auth_token)

    resp = VoiceResponse()

    text = base64.b64encode(text.encode()).decode() if text else "N"
    audio_url = base64.b64encode(audio_url.encode()).decode() if audio_url else "N"

    resp.redirect(
        get_route_url(
            twilio_voice_call_response,
            dict(bi_id=bi.id, text=text, audio_url=audio_url),
        )
    )

    call = client.calls.create(
        twiml=str(resp),
        to=user_phone_number,
        from_=bi.twilio_phone_number.as_e164,
    )

    return call


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
        sms_fallback_url=get_route_url(twilio_sms_error),
        sms_method="POST",
        sms_url=get_route_url(twilio_sms),
        # status_callback_method="POST", # uncomment for debugging
        # status_callback=get_route_url(twilio_voice_call_status),
        voice_fallback_method="POST",
        voice_fallback_url=get_route_url(twilio_voice_call_error),
        voice_method="POST",
        voice_url=get_route_url(twilio_voice_call),
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
        twilio_phone_number=PhoneNumber.from_string(twilio_phone_number),
        twilio_phone_number_sid=twilio_phone_number_sid,
    )
