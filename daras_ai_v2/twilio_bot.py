import uuid
from functools import cached_property

from loguru import logger
from twilio.base.exceptions import TwilioRestException
from twilio.twiml import TwiML
from twilio.twiml.voice_response import VoiceResponse

from bots.models import BotIntegration, Platform, Conversation
from daras_ai_v2 import settings
from daras_ai_v2.bots import BotInterface, ReplyButton
from daras_ai_v2.fastapi_tricks import get_api_route_url


class TwilioSMS(BotInterface):
    platform = Platform.TWILIO

    def __init__(self, data: dict):
        bi = BotIntegration.objects.get(twilio_phone_number=data["To"][0])
        self.convo = Conversation.objects.get_or_create(
            bot_integration=bi, twilio_phone_number=data["From"][0]
        )[0]

        self.bot_id = bi.twilio_phone_number.as_e164
        self.user_id = self.convo.twilio_phone_number.as_e164

        self._text = data["Body"][0]
        self.input_type = "text"

        self.user_msg_id = data["MessageSid"][0]

        super().__init__()

    def get_input_text(self) -> str | None:
        return self._text

    def _send_msg(
        self,
        *,
        text: str | None = None,
        audio: str | None = None,
        video: str | None = None,
        buttons: list[ReplyButton] | None = None,
        documents: list[str] | None = None,
        update_msg_id: str | None = None,
    ) -> str | None:
        assert buttons is None, "Interactive mode is not implemented yet"
        assert update_msg_id is None, "Twilio does not support un-sms-ing things"
        return send_sms_message(
            self.convo,
            text=text,
            media_url=audio or video or (documents[0] if documents else None),
        ).sid

    def mark_read(self):
        pass  # handled in the webhook


def send_sms_message(
    convo: Conversation, text: str | None, media_url: str | None = None
):
    """Send an SMS message to the given conversation."""

    assert (
        convo.twilio_phone_number
    ), "This is not a Twilio conversation, it has no phone number."

    client = convo.bot_integration.get_twilio_client()
    message = client.messages.create(
        body=text or "",
        media_url=media_url,
        from_=convo.bot_integration.twilio_phone_number.as_e164,
        to=convo.twilio_phone_number.as_e164,
    )

    return message


class TwilioVoice(BotInterface):
    platform = Platform.TWILIO

    @classmethod
    def from_data(cls, data: dict):
        ## data samples:
        # {'AccountSid': ['XXXX'], 'ApiVersion': ['2010-04-01'], 'CallSid': ['XXXX'], 'CallStatus': ['ringing'], 'CallToken': ['XXXX'], 'Called': ['XXXX'], 'CalledCity': ['XXXX'], 'CalledCountry': ['XXXX'], 'CalledState': ['XXXX'], 'CalledZip': ['XXXX'], 'Caller': ['XXXX'], 'CallerCity': ['XXXX'], 'CallerCountry': ['XXXX'], 'CallerState': ['XXXX'], 'CallerZip': ['XXXX'], 'Direction': ['inbound'], 'From': ['XXXX'], 'FromCity': ['XXXX'], 'FromCountry': ['XXXX'], 'FromState': ['XXXX'], 'FromZip': ['XXXX'], 'StirVerstat': ['XXXX'], 'To': ['XXXX'], 'ToCity': ['XXXX'], 'ToCountry': ['XXXX'], 'ToState': ['XXXX'], 'ToZip': ['XXXX']}
        # {'AccountSid': ['XXXX'], 'ApiVersion': ['2010-04-01'], 'CallSid': ['XXXX'], 'CallStatus': ['in-progress'], 'Called': ['XXXX'], 'CalledCity': ['XXXX'], 'CalledCountry': ['XXXX'], 'CalledState': ['XXXX'], 'CalledZip': ['XXXX'], 'Caller': ['XXXX'], 'CallerCity': ['XXXX'], 'CallerCountry': ['XXXX'], 'CallerState': ['XXXX'], 'CallerZip': ['XXXX'], 'Confidence': ['0.9128386'], 'Direction': ['inbound'], 'From': ['XXXX'], 'FromCity': ['XXXX'], 'FromCountry': ['XXXX'], 'FromState': ['XXXX'], 'FromZip': ['XXXX'], 'Language': ['en-US'], 'SpeechResult': ['Hello.'], 'To': ['XXXX'], 'ToCity': ['XXXX'], 'ToCountry': ['XXXX'], 'ToState': ['XXXX'], 'ToZip': ['XXXX']}
        # {'AccountSid': ['XXXX'], 'ApiVersion': ['2010-04-01'], 'CallSid': ['XXXX'], 'CallStatus': ['in-progress'], 'Called': ['XXXX'], 'CalledCity': ['XXXX'], 'CalledCountry': ['XXXX'], 'CalledState': ['XXXX'], 'CalledZip': ['XXXX'], 'Caller': ['XXXX'], 'CallerCity': ['XXXX'], 'CallerCountry': ['XXXX'], 'CallerState': ['XXXX'], 'CallerZip': ['XXXX'], 'Direction': ['inbound'], 'From': ['XXXX'], 'FromCity': ['XXXX'], 'FromCountry': ['XXXX'], 'FromState': ['XXXX'], 'FromZip': ['XXXX'], 'RecordingDuration': ['XXXX'], 'RecordingSid': ['XXXX'], 'RecordingUrl': ['https://api.twilio.com/2010-04-01/Accounts/AC5bac377df5bf25292fe863b9ddb2db2e/Recordings/RE0a6ed1afa9efaf42eb93c407b89619dd'], 'To': ['XXXX'], 'ToCity': ['XXXX'], 'ToCountry': ['XXXX'], 'ToState': ['XXXX'], 'ToZip': ['XXXX']}
        logger.debug(data)
        account_sid: str = data["AccountSid"][0] or ""
        if account_sid == settings.TWILIO_ACCOUNT_SID:
            account_sid = ""

        user_number, bot_number = data["From"][0], data["To"][0]
        try:
            # cases where user is calling the bot
            bi = BotIntegration.objects.get(
                twilio_account_sid=account_sid, twilio_phone_number=bot_number
            )
        except BotIntegration.DoesNotExist:
            #  cases where bot is calling the user
            user_number, bot_number = bot_number, user_number
            bi = BotIntegration.objects.get(
                twilio_account_sid=account_sid, twilio_phone_number=bot_number
            )

        convo = Conversation.objects.get_or_create(
            bot_integration=bi, twilio_phone_number=data["From"][0]
        )[0]
        return cls(
            convo,
            text=data.get("SpeechResult", [None])[0],
            audio_url=data.get("RecordingUrl", [None])[0],
            call_sid=data["CallSid"][0],
        )

    def __init__(
        self,
        convo: Conversation,
        *,
        call_sid: str = None,
        text: str = None,
        audio_url: str = None,
    ):
        self.convo = convo

        self.bot_id = convo.bot_integration.twilio_phone_number.as_e164
        self.user_id = convo.twilio_phone_number.as_e164

        self.call_sid = call_sid
        self.user_msg_id = f"{self.call_sid}-{uuid.uuid4()}"

        self._text = None
        self._audio_url = None
        if text:
            self.input_type = "text"
            self._text = text
        elif audio_url:
            self.input_type = "audio"
            self._audio_url = audio_url
        else:
            self.input_type = "interactive"

        super().__init__()

        self.use_gooey_asr = self.saved_run.state.get("asr_model")
        self.use_gooey_tts = self.saved_run.state.get("tts_provider")

    def get_input_text(self) -> str | None:
        return self._text

    def get_input_audio(self) -> str | None:
        return self._audio_url

    def _send_msg(
        self,
        *,
        text: str | None = None,
        audio: str | None = None,
        video: str | None = None,
        buttons: list[ReplyButton] | None = None,
        documents: list[str] | None = None,
        update_msg_id: str | None = None,
    ) -> str | None:
        from routers.twilio_api import twilio_voice_call_response

        assert documents is None, "Twilio does not support sending documents via Voice"
        assert video is None, "Twilio does not support sending videos via Voice"
        assert buttons is None, "Interactive mode is not implemented yet"
        assert update_msg_id is None, "Twilio does not support un-saying things"

        try:
            self.twilio_queue.members("Front").update(
                url=get_api_route_url(
                    twilio_voice_call_response,
                    query_params=dict(
                        convo_id=self.convo.id, text=text, audio_url=audio
                    ),
                ),
            )
        except TwilioRestException as e:
            if e.code == 20404:
                logger.error(
                    f"Call not found, probably already ended {self.call_sid=} {self.convo=}"
                )
            else:
                raise

        return f"{self.call_sid}-{uuid.uuid4()}"

    @cached_property
    def twilio_queue(self):
        return self.bi.get_twilio_client().queues.create(self.user_msg_id[:64])

    def mark_read(self):
        pass  # handled in the webhook

    def start_voice_call_session(self, resp: TwiML):
        client = self.bi.get_twilio_client()
        return client.calls.create(twiml=str(resp), from_=self.bot_id, to=self.user_id)


def send_single_voice_call(
    convo: Conversation, text: str | None, audio_url: str | None
):
    """Create a new voice call saying the given text and audio URL and then hanging up. Useful for notifications."""
    from routers.twilio_api import resp_say_or_tts_play

    assert (
        convo.twilio_phone_number
    ), "This is not a Twilio conversation, it has no phone number."

    bot = TwilioVoice(convo)

    resp = VoiceResponse()
    if audio_url:
        resp.play(audio_url)
    elif text:
        resp_say_or_tts_play(bot, resp, text)

    return bot.start_voice_call_session(resp)
