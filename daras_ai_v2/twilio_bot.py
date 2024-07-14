from bots.models import BotIntegration, Platform, Conversation
from daras_ai_v2.bots import BotInterface, ReplyButton
from phonenumber_field.phonenumber import PhoneNumber

from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from daras_ai_v2.fastapi_tricks import get_route_url

from uuid import uuid4
import base64


class TwilioSMS(BotInterface):
    platform = Platform.TWILIO

    def __init__(self, *, sid: str, convo: Conversation, text: str, bi: BotIntegration):
        self.convo = convo

        self._text = text
        self.input_type = "text"

        self.user_msg_id = sid
        self.bot_id = bi.id
        self.user_id = convo.twilio_phone_number.as_e164

        self._unpack_bot_integration()

    def get_input_text(self) -> str | None:
        return self._text

    def send_msg(
        self,
        *,
        text: str | None = None,
        audio: str | None = None,
        video: str | None = None,
        buttons: list[ReplyButton] | None = None,
        documents: list[str] | None = None,
        should_translate: bool = False,
        update_msg_id: str | None = None,
    ) -> str | None:
        assert buttons is None, "Interactive mode is not implemented yet"
        assert update_msg_id is None, "Twilio does not support un-sms-ing things"

        if should_translate:
            text = self.translate(text)

        return send_sms_message(
            self.convo,
            text=text,
            media_url=audio or video or (documents[0] if documents else None),
        ).sid

    def mark_read(self):
        pass  # handled in the webhook


class TwilioVoice(BotInterface):
    platform = Platform.TWILIO

    def __init__(
        self,
        *,
        incoming_number: str,
        queue_name: str,
        call_sid: str,
        text: str | None = None,
        audio: str | None = None,
        bi: BotIntegration,
    ):
        self.user_msg_id = uuid4().hex
        self._queue_name = queue_name
        self._call_sid = call_sid
        self.bot_id = bi.id
        self.user_id = incoming_number

        try:
            self.convo = Conversation.objects.get(
                twilio_phone_number=PhoneNumber.from_string(incoming_number),
                bot_integration=bi,
            )
        except Conversation.DoesNotExist:
            self.convo = Conversation.objects.get_or_create(
                twilio_phone_number=PhoneNumber.from_string(incoming_number),
                bot_integration=bi,
            )[0]

        if audio:
            self.input_type = "audio"
        else:
            self.input_type = "text"

        self._text = text
        self._audio = audio

        self._unpack_bot_integration()

    def get_input_text(self) -> str | None:
        return self._text

    def get_input_audio(self) -> str | None:
        return self._audio

    def send_msg(
        self,
        *,
        text: str | None = None,
        audio: str | None = None,
        video: str | None = None,
        buttons: list[ReplyButton] | None = None,
        documents: list[str] | None = None,
        should_translate: bool = False,
        update_msg_id: str | None = None,
    ) -> str | None:
        assert documents is None, "Twilio does not support sending documents via Voice"
        assert video is None, "Twilio does not support sending videos via Voice"
        assert buttons is None, "Interactive mode is not implemented yet"
        assert update_msg_id is None, "Twilio does not support un-saying things"

        # don't send both audio and text version of the same message
        if self.bi.twilio_default_to_gooey_tts and audio:
            text = None
        else:
            audio = None

        if should_translate:
            text = self.translate(text)

        twilio_voice_call_respond(
            text=text,
            audio_url=audio,
            queue_name=self._queue_name,
            call_sid=self._call_sid,
            bi=self.bi,
        )

        return uuid4().hex

    def mark_read(self):
        pass  # handled in the webhook


def twilio_voice_call_respond(
    text: str | None,
    audio_url: str | None,
    queue_name: str,
    call_sid: str,
    bi: BotIntegration,
):
    """Respond to the user in the queue with the given text and audio URL."""
    from routers.twilio_api import twilio_voice_call_response

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

    client.queues(queue_sid).members(call_sid).update(
        url=get_route_url(
            twilio_voice_call_response,
            dict(bi_id=bi.id, text=text, audio_url=audio_url),
        ),
        method="POST",
    )

    return queue_sid


def create_voice_call(convo: Conversation, text: str | None, audio_url: str | None):
    """Create a new voice call saying the given text and audio URL and then hanging up. Useful for notifications."""
    from routers.twilio_api import say

    assert (
        convo.twilio_phone_number
    ), "This is not a Twilio conversation, it has no phone number."

    bi: BotIntegration = convo.bot_integration
    client = Client(bi.twilio_account_sid, bi.twilio_auth_token)

    resp = VoiceResponse()
    if text:
        say(resp, text, bi)
    if audio_url:
        resp.play(audio_url)

    call = client.calls.create(
        twiml=str(resp),
        to=convo.twilio_phone_number.as_e164,
        from_=bi.twilio_phone_number.as_e164,
    )

    return call


def send_sms_message(
    convo: Conversation, text: str | None, media_url: str | None = None
):
    """Send an SMS message to the given conversation."""

    assert (
        convo.twilio_phone_number
    ), "This is not a Twilio conversation, it has no phone number."

    account_sid = convo.bot_integration.twilio_account_sid
    auth_token = convo.bot_integration.twilio_auth_token
    client = Client(account_sid, auth_token)

    message = client.messages.create(
        body=text or "",
        media_url=media_url,
        from_=convo.bot_integration.twilio_phone_number.as_e164,
        to=convo.twilio_phone_number.as_e164,
    )

    return message
