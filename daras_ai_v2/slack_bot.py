import requests
import json

from bots.models import BotIntegration, Platform, Conversation
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import settings
from daras_ai_v2.asr import run_google_translate
from daras_ai_v2.bots import BotInterface


class SlackBot(BotInterface):
    def __init__(
        self,
        message: dict[
            {
                "workspace_id": str,
                "application_id": str,
                "channel": str,
                "thread_ts": str,
                "text": str,
                "user": str,
            }
        ],
    ):
        self.input_message = message
        self.platform = Platform.SLACK

        self.bot_id = message["channel"]
        self.user_id = message["user"]

        self.input_type = "text"
        if message["files"]:
            self.input_type = (
                "audio" if "audio" in message["files"][0]["mimetype"] else "text"
            )

        bi = BotIntegration.objects.get(slack_channel_id=self.bot_id)
        self.name = bi.name
        self.convo = Conversation.objects.get_or_create(
            bot_integration=bi,
            slack_user_id=self.user_id,
        )[0]
        self._unpack_bot_integration(bi)

    def get_input_text(self) -> str | None:
        return self.input_message["text"]

    def get_input_audio(self) -> str | None:
        url = self.input_message.get("files", [{}])[0].get("url_private_download", "")
        if not url:
            return None
        r = requests.get(url)
        r.raise_for_status()
        mime_type = self.input_message.get("files", [{}])[0].get(
            "mimetype", "audio/mp4"
        )
        # upload file to firebase
        audio_url = upload_file_from_bytes(
            filename=self.nice_filename(mime_type),
            data=r.content,
            content_type=mime_type,
        )
        return audio_url

    def get_input_video(self) -> str | None:
        return None

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
        # TODO: handle buttons
        return reply(
            text=text,
            audio=audio,
            video=video,
            channel=self.bot_id,
            thread_ts=self.input_message["thread_ts"],
            username=self.name,
        )

    def mark_read(self):
        pass


def reply(
    text: str = None,
    audio: str = None,
    video: str = None,
    channel: str = None,
    thread_ts: str = None,
    username: str = "Video Bot",
):
    requests.post(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps(
            {
                "channel": channel,
                "thread_ts": thread_ts,
                "text": text,
                "username": username,
                "icon_emoji": ":robot_face:",
            }
        ),
        headers={
            "Authorization": f"Bearer {settings.SLACK_TOKEN}",
            "Content-type": "application/json",
        },
    )
