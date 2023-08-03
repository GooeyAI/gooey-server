import requests

from typing import TypedDict

from bots.models import BotIntegration, Platform, Conversation
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.text_splitter import text_splitter
from daras_ai_v2.asr import run_google_translate
from daras_ai_v2.bots import BotInterface

from langcodes import Language
from string import Template

SLACK_CONFIRMATION_MSG = """
Hi there! 👋

$name is now connected to your Slack workspace in this channel!

Invite my bot account to this channel by typing "@Gooey.AI Copilot" and selecting "Invite to Channel".

I'll then respond to any text and audio messages in this channel while keeping track of a separate conversation history with each user. Add 👍 or 👎 to my responses to help me learn.

I have been configured for $user_language and will respond to you in that language.
""".strip()

SLACK_MAX_SIZE = 4000


class SlackMessage(TypedDict):
    workspace_id: str
    application_id: str
    channel: str
    thread_ts: str
    text: str
    user: str
    files: list[dict]
    actions: list[dict]
    msg_id: str


class SlackBot(BotInterface):
    def __init__(
        self,
        message: SlackMessage,
    ):
        self.input_message = message  # type: ignore
        self.platform = Platform.SLACK

        self.bot_id = message["channel"]
        self.user_id = message["user"]

        self.input_type = "text"
        if message["files"]:
            self.input_type = (
                "audio" if "audio" in message["files"][0]["mimetype"] else "text"
            )
        if message["actions"]:
            self.input_type = "interactive"

        bi: BotIntegration = BotIntegration.objects.get(slack_channel_id=self.bot_id)
        self.name = bi.name
        self.slack_access_token = bi.slack_access_token
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
        r = requests.get(
            url, headers={"Authorization": f"Bearer {self.slack_access_token}"}
        )
        r.raise_for_status()
        print(r.text)
        mime_type = "audio/mp4"
        # upload file to firebase
        audio_url = upload_file_from_bytes(
            filename=self.nice_filename(mime_type),
            data=r.content,
            content_type=mime_type,
        )
        print("found audio url: " + audio_url)
        return audio_url

    def get_input_video(self) -> str | None:
        raise NotImplementedError()  # not used yet

    def get_interactive_msg_info(self) -> tuple[str, str]:
        return (
            self.input_message["actions"][0]["value"],
            self.input_message["msg_id"],
        )

    def send_msg(
        self,
        *,
        text: str | None = None,
        audio: str | None = None,
        video: str | None = None,
        buttons: list | None = None,
        should_translate: bool = False,
    ) -> str | None:
        if not text:  # TODO: handle audio/video
            return None
        if should_translate and self.language and self.language != "en":
            text = run_google_translate([text], self.language)[0]
        splits = text_splitter(text, chunk_size=SLACK_MAX_SIZE, length_function=len)
        for doc in splits[:-1]:
            reply(
                text=doc.text,
                audio=audio,
                video=video,
                channel=self.bot_id,
                thread_ts=self.input_message["thread_ts"],
                username=self.name,
                token=self.slack_access_token,
                buttons=[],
            )
        msg_id = reply(
            text=splits[-1].text,
            audio=audio,
            video=video,
            channel=self.bot_id,
            thread_ts=self.input_message["thread_ts"],
            username=self.name,
            token=self.slack_access_token,
            buttons=buttons or [],
        )
        return msg_id

    def mark_read(self):
        pass


def reply(
    text: str,
    channel: str,
    thread_ts: str,
    audio: str | None = None,
    video: str | None = None,
    username: str = "Video Bot",
    token: str | None = None,
    buttons: list = None,
):
    if buttons is None:
        buttons = []
    res = requests.post(
        "https://slack.com/api/chat.postMessage",
        json={
            "channel": channel,
            "thread_ts": thread_ts,
            "text": text,
            "username": username,
            "icon_emoji": ":robot_face:",
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "plain_text", "text": text},
                },
            ]
            + create_button_block(buttons),
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )
    return res.json().get("ts", thread_ts)


def create_button_block(
    buttons: list[dict[{"type": str, "reply": dict[{"id": str, "title": str}]}]]
) -> list[dict]:
    if not buttons:
        return []
    elements = []
    for button in buttons:
        element = {}
        element["type"] = "button"
        element["text"] = {"type": "plain_text", "text": button["reply"]["title"]}
        element["value"] = button["reply"]["id"]
        element["action_id"] = "button_" + button["reply"]["id"]
        elements.append(element)

    return [
        {
            "type": "actions",
            "elements": elements,
        }
    ]


def send_confirmation_msg(bot: BotIntegration):
    substitutions = vars(bot).copy()  # convert to dict for string substitution
    substitutions["user_language"] = Language.get(
        bot.user_language,
    ).display_name()
    text = run_google_translate(
        [Template(SLACK_CONFIRMATION_MSG).safe_substitute(**substitutions)],
        target_language=bot.user_language,
        source_language="en",
    )[0]
    print("confirmation msg: " + text)
    res = requests.post(
        str(bot.slack_channel_hook_url),
        json={"text": text},
    )
    res.raise_for_status()
