import requests

from bots.models import BotIntegration, Platform, Conversation
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import settings
from daras_ai_v2.asr import run_google_translate
from daras_ai_v2.text_splitter import text_splitter
from daras_ai_v2.bots import BotInterface


class SlackBot(BotInterface):
    def __init__(self, message: dict, metadata: dict):
        self.input_message = message
        self.platform = Platform.SLACK

        self.bot_id = metadata["phone_number_id"]  # this is NOT the phone number
        self.user_id = message["from"]  # this is a phone number

        self.input_type = message["type"]

        bi = BotIntegration.objects.get(wa_phone_number_id=self.bot_id)
        self.convo = Conversation.objects.get_or_create(
            bot_integration=bi,
            wa_phone_number="+" + self.user_id,
        )[0]
        self._unpack_bot_integration(bi)

    def get_input_text(self) -> str | None:
        try:
            return self.input_message["text"]["body"]
        except KeyError:
            return None

    def get_input_audio(self) -> str | None:
        try:
            media_id = self.input_message["audio"]["id"]
        except KeyError:
            return None
        return self._download_wa_media(media_id)

    def get_input_video(self) -> str | None:
        try:
            media_id = self.input_message["video"]["id"]
        except KeyError:
            return None
        return self._download_wa_media(media_id)

    def _download_wa_media(self, media_id: str) -> str:
        # download file from whatsapp
        content, mime_type = retrieve_wa_media_by_id(media_id)
        # upload file to firebase
        return upload_file_from_bytes(
            filename=self.nice_filename(mime_type),
            data=content,
            content_type=mime_type,
        )

    def send_msg(
        self,
        *,
        text: str = None,
        audio: str = None,
        video: str = None,
        buttons: list = None,
        should_translate: bool = False,
    ) -> str | None:
        if should_translate and self.language and self.language != "en":
            text = run_google_translate([text], self.language)[0]
        return send_wa_msg(
            bot_number=self.bot_id,
            user_number=self.user_id,
            response_text=text,
            response_audio=audio,
            response_video=video,
            buttons=buttons,
        )

    def mark_read(self):
        wa_mark_read(self.bot_id, self.input_message["id"])
