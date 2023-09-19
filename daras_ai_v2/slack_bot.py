import re
import typing
from string import Template
from typing import TypedDict

import requests
from django.db import transaction
from langcodes import Language
from requests import Response
from sentry_sdk import capture_exception

from bots.models import BotIntegration, Platform, Conversation
from daras_ai.image_input import upload_file_from_bytes, get_mimetype_from_response
from daras_ai_v2.asr import run_google_translate, audio_bytes_to_wav
from daras_ai_v2.bots import BotInterface
from daras_ai_v2.functional import fetch_parallel
from daras_ai_v2.text_splitter import text_splitter

SLACK_CONFIRMATION_MSG = """
Hi there! 👋

$name is now connected to your Slack workspace in this channel!

I'll respond to any text and audio messages in this channel while keeping track of a separate conversation history with each user. Add 👍 or 👎 to my responses to help me learn.

I have been configured for $user_language and will respond to you in that language.
""".strip()

SLACK_MAX_SIZE = 3000


class SlackMessage(TypedDict):
    application_id: str
    channel: str
    thread_ts: str
    text: str
    user_id: str
    files: list[dict]
    actions: list[dict]
    msg_id: str
    team_id: str


class SlackBot(BotInterface):
    _read_msg_id: str | None = None

    def __init__(
        self,
        message: SlackMessage,
    ):
        self.input_message = message  # type: ignore
        self.platform = Platform.SLACK

        self.bot_id = message["channel"]
        self.user_id = message["user_id"]

        self.input_type = "text"
        files = message.get("files", [])
        if files:
            self.input_type = files[0].get("media_display_type", "")
        if message.get("actions"):
            self.input_type = "interactive"

        # Try to find an existing conversation, this could either be a personal channel or the main channel the integration was added to
        try:
            self.convo = Conversation.objects.get(
                slack_channel_id=self.bot_id,
                slack_user_id=self.user_id,
                slack_team_id=message["team_id"],
            )
        except Conversation.DoesNotExist:
            # No existing conversation found, this could be a personal channel or the main channel the integration was added to
            # find the bot integration for this main channel and use it to create a new conversation
            self.convo = Conversation.objects.get_or_create(
                slack_channel_id=self.bot_id,
                slack_user_id=self.user_id,
                slack_team_id=message["team_id"],
                defaults=dict(
                    bot_integration=BotIntegration.objects.get(
                        slack_channel_id=self.bot_id,
                        slack_team_id=message["team_id"],
                    ),
                ),
            )[0]

        fetch_missing_convo_metadata(self.convo)

        bi = self.convo.bot_integration
        self.name = bi.name
        self.slack_access_token = bi.slack_access_token
        self.read_msg = bi.slack_read_receipt_msg.strip()
        self._unpack_bot_integration(bi)

        self._thread_ts = message["thread_ts"]

    def get_input_text(self) -> str | None:
        return self.input_message["text"]

    def get_input_audio(self) -> str | None:
        files = self.input_message.get("files", [])
        if not files:
            return None
        url = files[0].get("url_private_download", "")
        if not url:
            return None
        # download file from slack
        r = requests.get(
            url, headers={"Authorization": f"Bearer {self.slack_access_token}"}
        )
        r.raise_for_status()
        # ensure file is audio/video
        mime_type = get_mimetype_from_response(r)
        assert (
            "audio/" in mime_type or "video/" in mime_type
        ), f"Invalid mime type {mime_type} for {url}"
        # convert to wav
        data, _ = audio_bytes_to_wav(r.content)
        mime_type = "audio/wav"
        # upload file to firebase
        audio_url = upload_file_from_bytes(
            filename=self.nice_filename(mime_type),
            data=data,
            content_type=mime_type,
        )
        return audio_url

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
        if not text:
            return None
        if should_translate and self.language and self.language != "en":
            text = run_google_translate([text], self.language)[0]

        if self._read_msg_id and self._read_msg_id != self._thread_ts:
            delete_msg(
                channel=self.bot_id,
                thread_ts=self._read_msg_id,
                token=self.slack_access_token,
            )
            self._read_msg_id = None

        splits = text_splitter(text, chunk_size=SLACK_MAX_SIZE, length_function=len)
        for doc in splits[:-1]:
            self._thread_ts = chat_post_message(
                text=doc.text,
                channel=self.bot_id,
                channel_is_personal=self.convo.slack_channel_is_personal,
                thread_ts=self._thread_ts,
                username=self.name,
                token=self.slack_access_token,
            )
        self._thread_ts = chat_post_message(
            text=splits[-1].text,
            audio=audio,
            video=video,
            channel=self.bot_id,
            channel_is_personal=self.convo.slack_channel_is_personal,
            thread_ts=self._thread_ts,
            username=self.name,
            token=self.slack_access_token,
            buttons=buttons or [],
        )
        return self._thread_ts

    def mark_read(self):
        if not self.read_msg:
            return
        text = self.read_msg
        if self.language and self.language != "en":
            text = run_google_translate([text], self.language)[0]
        self._read_msg_id = chat_post_message(
            text=text,
            channel=self.bot_id,
            channel_is_personal=self.convo.slack_channel_is_personal,
            thread_ts=self._thread_ts,
            token=self.slack_access_token,
        )


def delete_msg(
    channel: str,
    thread_ts: str,
    token: str,
):
    res = requests.post(
        "https://slack.com/api/chat.delete",
        json={"channel": channel, "ts": thread_ts},
        headers={"Authorization": f"Bearer {token}"},
    )
    parse_slack_response(res)


def create_personal_channels_for_all_members(bi: BotIntegration):
    for user in fetch_channel_members(bi.slack_channel_id, bi.slack_access_token):
        create_personal_channel(bi, user)


def fetch_channel_members(
    channel: str,
    token: str,
    cursor: str | None = None,
) -> typing.Generator[dict, None, None]:
    query_params = {"channel": channel, "limit": "1000"}
    if cursor:
        query_params["cursor"] = cursor
    res = requests.get(
        "https://slack.com/api/conversations.members",
        params=query_params,
        headers={"Authorization": f"Bearer {token}"},
    )
    data = parse_slack_response(res)
    yield from fetch_parallel(
        lambda user_id: fetch_user_info(user_id, token), data["members"]
    )
    cursor = data.get("response_metadata", {}).get("next_cursor")
    if not cursor:
        return
    for user_id in fetch_channel_members(channel, token, cursor):
        yield user_id


def fetch_missing_convo_metadata(convo: Conversation):
    try:
        token = convo.bot_integration.slack_access_token
        if not convo.slack_user_name:
            user_data = fetch_user_info(convo.slack_user_id, token)
            Conversation.objects.filter(id=convo.id).update(
                slack_user_name=user_data["real_name"]
            )
        if not convo.slack_channel_name:
            channel_data = fetch_channel_info(convo.slack_channel_id, token)
            Conversation.objects.filter(id=convo.id).update(
                slack_channel_name=channel_data["name"]
            )
    except SlackAPIError as e:
        if e.error == "missing_scope":
            print(f"Error: Missing scopes for - {convo!r}")
            capture_exception(e)
        else:
            raise


def fetch_channel_info(channel: str, token: str) -> dict[str, typing.Any]:
    res = requests.get(
        "https://slack.com/api/conversations.info",
        params={"channel": channel},
        headers={"Authorization": f"Bearer {token}"},
    )
    data = parse_slack_response(res)
    return data["channel"]


def fetch_user_info(user_id: str, token: str) -> dict[str, typing.Any]:
    res = requests.get(
        "https://slack.com/api/users.info",
        params={"user": user_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    data = parse_slack_response(res)
    return data["user"]


# https://api.slack.com/methods/conversations.rename#naming
CHANNEL_NAME_WHITELIST = re.compile(r"[a-z0-9-_]")
CHANNEL_NAME_MAX_LENGTH = 80


def safe_channel_name(name: str) -> str:
    name = name.lower().replace(" ", "-")
    name = "".join(CHANNEL_NAME_WHITELIST.findall(name))
    name = name[:CHANNEL_NAME_MAX_LENGTH]
    name = name.rstrip("-_")
    return name


def create_personal_channel(
    bi: BotIntegration,
    user: dict,
    *,
    max_tries: int = 5,
) -> Conversation | None:
    if user["is_bot"]:
        return None
    user_id = user["id"]
    user_name = user["real_name"]
    team_id = user["team_id"]
    # lookup the personal convo with this bot and user
    convo_lookup = dict(
        bot_integration=bi,
        slack_user_id=user_id,
        slack_team_id=team_id,
        slack_channel_is_personal=True,
    )
    # if the slack channel exists, don't create a new one
    convo = check_personal_convo_exists(convo_lookup, bi.slack_access_token)
    if convo:
        channel_id = convo.slack_channel_id
        channel_name = convo.slack_channel_name
    else:
        channel_id, channel_name = create_personal_channel_brute_force(
            bi, user_name, max_tries
        )
    # set the topic and invite the user to the channel
    set_slack_channel_topic(
        bot_name=bi.name,
        channel_id=channel_id,
        token=bi.slack_access_token,
    )
    invite_user_to_channel(
        user_id=user_id,
        channel_id=channel_id,
        token=bi.slack_access_token,
    )
    # ensure the metadata like user name is up to date
    convo_defaults = dict(
        slack_user_name=user_name,
        slack_channel_id=channel_id,
        slack_channel_name=channel_name,
    )
    # create the conversation and update the metadata
    with transaction.atomic():
        bi, created = Conversation.objects.get_or_create(
            **convo_lookup,
            defaults=convo_defaults,
        )
        if not created:
            Conversation.objects.filter(pk=bi.pk).update(**convo_defaults)
    return bi


def check_personal_convo_exists(
    convo_lookup: dict, access_token: str
) -> Conversation | None:
    try:
        convo = Conversation.objects.get(**convo_lookup)
    except Conversation.DoesNotExist:
        return None
    if check_channel_exists(convo.slack_channel_id, access_token):
        return convo
    else:
        return None


def create_personal_channel_brute_force(
    bi: BotIntegration, user_name: str, max_tries: int
) -> tuple[str, str]:
    i = 0
    while True:
        try:
            channel_name_parts = [bi.slack_channel_name or bi.name, user_name, i]
            channel_name = safe_channel_name(
                "-".join(map(str, filter(None, channel_name_parts))),
            )
            channel_id = create_channel(
                channel_name=channel_name,
                is_private=True,
                token=bi.slack_access_token,
            )
        except ChannelAlreadyExists:
            i += 1
            if i > max_tries:
                raise
        else:
            break
    return channel_id, channel_name


def check_channel_exists(channel_id: str, token: str) -> bool:
    res = requests.get(
        "https://slack.com/api/conversations.info",
        params={"channel": channel_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        data = parse_slack_response(res)
    except SlackAPIError as e:
        if e.error == "channel_not_found":
            return False
        else:
            raise
    if data["channel"]["is_archived"]:
        res = requests.post(
            "https://slack.com/api/conversations.unarchive",
            params={"channel": channel_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        parse_slack_response(res)
    return True


def set_slack_channel_topic(
    *,
    bot_name: str,
    channel_id: str,
    token: str,
):
    res = requests.post(
        "https://slack.com/api/conversations.setTopic",
        json={
            "channel": channel_id,
            "topic": (
                f"Your personal conversation with {bot_name}. "
                "This is a separate conversation history from the public channel and other people can't view your messages."
            ),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    parse_slack_response(res)


def invite_user_to_channel(
    *,
    user_id: str,
    channel_id: str,
    token: str,
):
    res = requests.post(
        "https://slack.com/api/conversations.invite",
        json={
            "channel": channel_id,
            "users": user_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        parse_slack_response(res)
    except SlackAPIError as e:
        if e.error not in ["already_in_channel", "cant_invite_self"]:
            raise


def create_channel(*, channel_name: str, is_private: bool, token: str) -> str | None:
    res = requests.post(
        "https://slack.com/api/conversations.create",
        json={"name": channel_name, "is_private": is_private},
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        data = parse_slack_response(res)
    except SlackAPIError as e:
        if e.error == "name_taken":
            raise ChannelAlreadyExists() from e
        raise
    return data["channel"]["id"]


class ChannelAlreadyExists(Exception):
    pass


def chat_post_message(
    *,
    text: str,
    channel: str,
    thread_ts: str,
    token: str,
    channel_is_personal: bool = False,
    audio: str | None = None,
    video: str | None = None,
    username: str = "Video Bot",
    buttons: list | None = None,
) -> str | None:
    if buttons is None:
        buttons = []
    if channel_is_personal:
        # don't thread in personal channels
        thread_ts = None
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
                    "text": {"type": "mrkdwn", "text": text},
                },
            ]
            + create_file_block("Audio", token, audio)
            + create_file_block("Video", token, video)
            + create_button_block(buttons),
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )
    data = parse_slack_response(res)
    return data.get("ts")


def create_file_block(
    title: str,
    token: str,
    url: str | None = None,
) -> list[dict]:
    if not url:
        return []
    res = requests.get(
        "https://slack.com/api/files.remote.add",
        params={
            "external_id": url,
            "external_url": url,
            "title": title,
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )
    parse_slack_response(res)
    return [
        {
            "type": "file",
            "external_id": url,
            "source": "remote",
        },
    ]


def create_button_block(
    buttons: list[
        dict[{"type": str, "chat_post_message": dict[{"id": str, "title": str}]}]
    ]
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
    res = requests.post(
        str(bot.slack_channel_hook_url),
        json={"text": text},
    )
    res.raise_for_status()


def invite_bot_account_to_channel(channel: str, bot_user_id: str, token: str):
    res = requests.post(
        "https://slack.com/api/conversations.invite",
        json={"channel": channel, "users": bot_user_id},
        headers={
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        parse_slack_response(res)
    except SlackAPIError as e:
        if e.error != "already_in_channel":
            raise


def parse_slack_response(res: Response):
    res.raise_for_status()
    data = res.json()
    print(">", res.request.url.split("/")[-1] + ":", data)
    if data.get("ok"):
        return data
    else:
        raise SlackAPIError(data.get("error", data))


class SlackAPIError(Exception):
    def __init__(self, error: str | dict):
        self.error = error
        super().__init__(error)
