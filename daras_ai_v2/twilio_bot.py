import uuid
from functools import cached_property
from time import sleep

import aifail
import requests
from loguru import logger
from twilio.base.exceptions import TwilioRestException
from twilio.twiml import TwiML
from twilio.twiml.voice_response import VoiceResponse

from bots.models import BotIntegration, Platform, Conversation
from daras_ai_v2 import settings
from daras_ai_v2.bots import BotInterface, ReplyButton
from daras_ai_v2.fastapi_tricks import get_api_route_url
from django.utils import timezone
from django.db import transaction
from number_cycling.models import ProvisionedNumber, BotExtensionUser
from sentry_sdk import capture_exception

DISCONNECT_EXTENSION_TEXT = "Extension disconnected"

INITIATE_EXTENSION_TEXT = "Hi from Gooey.AI, Please enter your extension number"


class ExtensionGatheringSMS(Exception):
    """Exception raised when a user needs to provide an extension number."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class TwilioSMS(BotInterface):
    platform = Platform.TWILIO

    @classmethod
    def from_webhook_data(cls, data: dict):
        account_sid = data["AccountSid"][0]
        if account_sid == settings.TWILIO_ACCOUNT_SID:
            account_sid = ""
        bot_extension = None
        is_provisioned = False
        user_id = data["From"][0]
        bot_id = data["To"][0]

        try:
            ProvisionedNumber.objects.get(phone_number=bot_id, is_active=True)
            is_provisioned = True
            try:
                extension_user = BotExtensionUser.objects.get(
                    twilio_phone_number=user_id,
                    extension__bot_integration__twilio_phone_number=bot_id,
                )
            except BotExtensionUser.DoesNotExist:
                raise ExtensionGatheringSMS(INITIATE_EXTENSION_TEXT)

            bot_extension = extension_user.extension
            bi = bot_extension.bot_integration

        except ProvisionedNumber.DoesNotExist:
            bi = BotIntegration.objects.get(
                twilio_account_sid=account_sid, twilio_phone_number=bot_id
            )

        convo = (
            Conversation.objects.filter(
                bot_integration=bi,
                twilio_phone_number=user_id,
                twilio_call_sid="",
                extension=bot_extension,
            )
            .order_by("created_at")
            .last()
        )

        if not convo:
            with transaction.atomic():
                convo = Conversation.objects.create(
                    bot_integration=bi,
                    twilio_phone_number=user_id,
                    twilio_call_sid="",
                    extension=bot_extension,
                )

        text, media_urls, input_type = cls._extract_media_info(data)
        user_msg_id = data["MessageSid"][0]

        if is_provisioned:
            try:
                handle_disconnect_ext_twilio(text, user_id, convo)
            except ExtensionGatheringSMS:
                raise

        return cls(
            convo,
            text=text,
            media_urls=media_urls,
            input_type=input_type,
            user_msg_id=user_msg_id,
        )

    @staticmethod
    def _extract_media_info(data: dict) -> tuple[str, list[str], str]:
        """Extract media information from webhook data."""
        num_media = int(data.get("NumMedia", [0])[0])
        if num_media > 0:
            text = ""
            media_urls = [data[f"MediaUrl{i}"][0] for i in range(num_media)]
            content_type = data.get("MediaContentType0", [""])[0]
            if content_type.startswith("image/"):
                input_type = "image"
            elif content_type.startswith("audio/"):
                input_type = "audio"
            elif content_type.startswith("video/"):
                input_type = "video"
            else:
                input_type = "document"
        else:
            text = data["Body"][0]
            media_urls = []
            input_type = "text"

        return text, media_urls, input_type

    def __init__(
        self,
        convo: Conversation,
        text: str | None,
        media_urls: list[str] | None,
        input_type: str,
        user_msg_id: str,
    ):
        self.convo = convo
        self.bot_id = convo.bot_integration.twilio_phone_number.as_e164
        self.user_id = convo.twilio_phone_number.as_e164
        self.input_type = input_type
        self.user_msg_id = user_msg_id
        self._text = text
        self._media_urls = media_urls
        super().__init__()

    def get_input_text(self) -> str | None:
        return self._text

    def get_input_audio(self) -> str | None:
        return self._media_urls and self._media_urls[0]

    def get_input_images(self) -> list[str] | None:
        return self._media_urls

    def get_input_documents(self) -> list[str] | None:
        return self._media_urls

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
        assert not buttons, "Interactive mode is not implemented yet"
        media = audio or video or documents
        return send_sms_message(
            self.convo,
            text=text,
            media_url=media and media[0] or None,
        ).sid

    def mark_read(self):
        pass  # handled in the webhook


def send_sms_message(
    convo: Conversation, text: str | None, media_url: str | None = None
):
    """Send an SMS message to the given conversation."""

    assert convo.twilio_phone_number, (
        "This is not a Twilio conversation, it has no phone number."
    )

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
    def from_webhook_data(cls, data: dict):
        ## data samples:
        # {'AccountSid': ['XXXX'], 'ApiVersion': ['2010-04-01'], 'CallSid': ['XXXX'], 'CallStatus': ['ringing'], 'CallToken': ['XXXX'], 'Called': ['XXXX'], 'CalledCity': ['XXXX'], 'CalledCountry': ['XXXX'], 'CalledState': ['XXXX'], 'CalledZip': ['XXXX'], 'Caller': ['XXXX'], 'CallerCity': ['XXXX'], 'CallerCountry': ['XXXX'], 'CallerState': ['XXXX'], 'CallerZip': ['XXXX'], 'Direction': ['inbound'], 'From': ['XXXX'], 'FromCity': ['XXXX'], 'FromCountry': ['XXXX'], 'FromState': ['XXXX'], 'FromZip': ['XXXX'], 'StirVerstat': ['XXXX'], 'To': ['XXXX'], 'ToCity': ['XXXX'], 'ToCountry': ['XXXX'], 'ToState': ['XXXX'], 'ToZip': ['XXXX']}
        # {'AccountSid': ['XXXX'], 'ApiVersion': ['2010-04-01'], 'CallSid': ['XXXX'], 'CallStatus': ['in-progress'], 'Called': ['XXXX'], 'CalledCity': ['XXXX'], 'CalledCountry': ['XXXX'], 'CalledState': ['XXXX'], 'CalledZip': ['XXXX'], 'Caller': ['XXXX'], 'CallerCity': ['XXXX'], 'CallerCountry': ['XXXX'], 'CallerState': ['XXXX'], 'CallerZip': ['XXXX'], 'Confidence': ['0.9128386'], 'Direction': ['inbound'], 'From': ['XXXX'], 'FromCity': ['XXXX'], 'FromCountry': ['XXXX'], 'FromState': ['XXXX'], 'FromZip': ['XXXX'], 'Language': ['en-US'], 'SpeechResult': ['Hello.'], 'To': ['XXXX'], 'ToCity': ['XXXX'], 'ToCountry': ['XXXX'], 'ToState': ['XXXX'], 'ToZip': ['XXXX']}
        # {'AccountSid': ['XXXX'], 'ApiVersion': ['2010-04-01'], 'CallSid': ['XXXX'], 'CallStatus': ['in-progress'], 'Called': ['XXXX'], 'CalledCity': ['XXXX'], 'CalledCountry': ['XXXX'], 'CalledState': ['XXXX'], 'CalledZip': ['XXXX'], 'Caller': ['XXXX'], 'CallerCity': ['XXXX'], 'CallerCountry': ['XXXX'], 'CallerState': ['XXXX'], 'CallerZip': ['XXXX'], 'Direction': ['inbound'], 'From': ['XXXX'], 'FromCity': ['XXXX'], 'FromCountry': ['XXXX'], 'FromState': ['XXXX'], 'FromZip': ['XXXX'], 'RecordingDuration': ['XXXX'], 'RecordingSid': ['XXXX'], 'RecordingUrl': ['https://api.twilio.com/2010-04-01/Accounts/AC5bac377df5bf25292fe863b9ddb2db2e/Recordings/RE0a6ed1afa9efaf42eb93c407b89619dd'], 'To': ['XXXX'], 'ToCity': ['XXXX'], 'ToCountry': ['XXXX'], 'ToState': ['XXXX'], 'ToZip': ['XXXX']}
        logger.debug(data)
        account_sid = data["AccountSid"][0]
        if account_sid == settings.TWILIO_ACCOUNT_SID:
            account_sid = ""
        call_sid = data["CallSid"][0]
        user_number, bot_number = data["From"][0], data["To"][0]
        try:
            # cases where user is calling the bot
            bi = BotIntegration.objects.get(
                twilio_account_sid=account_sid, twilio_phone_number=bot_number
            )
            will_be_missed = bi.twilio_use_missed_call
        except BotIntegration.DoesNotExist:
            #  cases where bot is calling the user
            user_number, bot_number = bot_number, user_number
            bi = BotIntegration.objects.get(
                twilio_account_sid=account_sid, twilio_phone_number=bot_number
            )
            will_be_missed = False

        if will_be_missed:
            # for calls that we will reject and callback, the convo is not used so we don't want to create one
            convo = Conversation(
                bot_integration=bi,
                twilio_phone_number=user_number,
                twilio_call_sid=call_sid,
            )
        elif bi.twilio_fresh_conversation_per_call:
            convo = Conversation.objects.get_or_create(
                bot_integration=bi,
                twilio_phone_number=user_number,
                twilio_call_sid=call_sid,
            )[0]
        else:
            convo = Conversation.objects.get_or_create(
                bot_integration=bi,
                twilio_phone_number=user_number,
                twilio_call_sid="",
            )[0]

        return cls(
            convo,
            text=data.get("SpeechResult", [None])[0],
            audio_url=data.get("RecordingUrl", [None])[0],
            call_sid=call_sid,
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
            if requests.head(audio_url).status_code == 404:
                sleep(1)  # wait for the recording to be available
        else:
            self.input_type = "interactive"

        super().__init__()

    def get_input_text(self) -> str | None:
        return self._text

    def get_input_audio(self) -> str | None:
        return self._audio_url

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
        assert not documents, "Twilio does not support sending documents via Voice"
        assert not video, "Twilio does not support sending videos via Voice"
        assert not buttons, "Interactive mode is not implemented yet"

        try:
            return send_msg_to_queue(
                self.twilio_queue, convo_id=self.convo.id, text=text, audio=audio
            )
        except Exception as e:
            if is_queue_not_found(e):
                logger.error(f"Call queue not found, probably already ended. {e=}")
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


def is_queue_not_found(exc: Exception):
    return isinstance(exc, TwilioRestException) and exc.code == 20404


@aifail.retry_if(is_queue_not_found, max_retry_delay=6, max_retries=10)
def send_msg_to_queue(
    queue, *, convo_id: int, text: str | None, audio: list[str] | None
):
    from routers.twilio_api import twilio_voice_call_response

    return queue.members("Front").update(
        url=get_api_route_url(
            twilio_voice_call_response,
            query_params=dict(convo_id=convo_id, text=text, audio=audio),
        )
    )


def send_single_voice_call(
    convo: Conversation, text: str | None, audio_url: str | None
):
    """Create a new voice call saying the given text and audio URL and then hanging up. Useful for notifications."""
    from routers.twilio_api import resp_say_or_tts_play

    assert convo.twilio_phone_number, (
        "This is not a Twilio conversation, it has no phone number."
    )

    bot = TwilioVoice(convo)

    resp = VoiceResponse()
    if audio_url:
        resp.play(audio_url)
    elif text:
        resp_say_or_tts_play(bot, resp, text)

    return bot.start_voice_call_session(resp)


def handle_disconnect_ext_twilio(text: str, user_id: str, convo: Conversation):
    from daras_ai_v2.bots import DISCONNECT_EXT_KEYWORDS

    if text and text.lower() in DISCONNECT_EXT_KEYWORDS:
        with transaction.atomic():
            try:
                extension_user = BotExtensionUser.objects.get(
                    twilio_phone_number=user_id,
                    extension__bot_integration__twilio_phone_number=convo.bot_integration.twilio_phone_number,
                )

                extension_user.delete()
            except BotExtensionUser.DoesNotExist as e:
                capture_exception(e)

                return

            convo.reset_at = timezone.now()
            convo.save()
        raise ExtensionGatheringSMS(DISCONNECT_EXTENSION_TEXT)
