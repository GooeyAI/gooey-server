from bots.models import BotIntegration, Platform, Conversation
from daras_ai_v2.bots import BotInterface, ReplyButton

from daras_ai_v2.asr import run_google_translate, should_translate_lang


class TwilioSMS(BotInterface):
    pass


class TwilioVoice(BotInterface):
    platform = Platform.TWILIO

    def __init__(
        self,
        *,
        incoming_number: str,
        queue_name: str,
        text: str | None = None,
        audio: str | None = None,
        bi: BotIntegration,
    ):
        self.user_msg_id = queue_name
        self.bot_id = bi.id
        self.user_id = incoming_number

        try:
            self.convo = Conversation.objects.get(
                twilio_phone_number=incoming_number,
                bot_integration=bi,
            )
        except Conversation.DoesNotExist:
            self.convo = Conversation.objects.get_or_create(
                twilio_phone_number=incoming_number,
                bot_integration=bi,
            )[0]

        if (
            audio
            and bi.twilio_default_to_gooey_asr
            and bi.saved_run.state.get("asr_model")
        ):
            self.input_type = "audio"
        else:
            self.input_type = "text"

        self._text = text
        self._audio = audio

        self._unpack_bot_integration()
        self.bi = bi

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
        buttons: list[ReplyButton] = None,
        documents: list[str] = None,
        should_translate: bool = False,
        update_msg_id: str | None = None,
    ) -> str | None:
        from routers.twilio_api import twilio_voice_call_respond

        assert documents is None, "Twilio does not support sending documents via Voice"
        assert video is None, "Twilio does not support sending videos via Voice"
        assert buttons is None, "Interactive mode is not implemented yet"
        assert update_msg_id is None, "Twilio does not support un-saying things"

        if self.bi.twilio_default_to_gooey_tts and audio:
            text = None
        else:
            audio = None

        if text and should_translate and should_translate_lang(self.language):
            text = run_google_translate(
                [text], self.language, glossary_url=self.output_glossary
            )[0]

        return twilio_voice_call_respond(
            text=text,
            audio_url=audio,
            user_phone_number=self.user_id,
            queue_name=self.user_msg_id,
            bi=self.bi,
        )

    def mark_read(self):
        pass  # handled in the webhook
