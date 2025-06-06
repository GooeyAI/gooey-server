import mimetypes
import re
import typing
from string import Template

import requests
from django.db import transaction
from requests import Response
from sentry_sdk import capture_exception

from bots.models import BotIntegration, Platform, Conversation
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.asr import (
    audio_bytes_to_wav,
)
from daras_ai_v2.bots import BotInterface, SLACK_MAX_SIZE, ButtonPressed
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.functional import fetch_parallel
from daras_ai_v2.search_ref import SearchReference
from daras_ai_v2.text_splitter import text_splitter
from recipes.VideoBots import ReplyButton

SLACK_CONFIRMATION_MSG = """
Hi there! 👋

$name is now connected to your Slack workspace in this channel!

I'll respond to any text and audio messages in this channel while keeping track of a separate conversation history with each user. Add 👍 or 👎 to my responses to help me learn.
""".strip()


class SlackBot(BotInterface):
    platform = Platform.SLACK
    can_update_message = True

    _read_rcpt_ts: str | None = None

    def __init__(
        self,
        *,
        message_ts: str,
        team_id: str,
        channel_id: str,
        user_id: str,
        text: str = "",
        files: list[dict] = None,
        actions: list[dict] = None,
    ):
        self.user_msg_id = self._msg_ts = message_ts
        self._team_id = team_id
        self.bot_id = channel_id
        self.user_id = user_id
        self._text = text

        # Try to find an existing conversation, this could either be a personal channel or the main channel the integration was added to
        try:
            self.convo = Conversation.objects.get(
                slack_channel_id=self.bot_id,
                slack_user_id=self.user_id,
                slack_team_id=self._team_id,
            )
        except Conversation.DoesNotExist:
            # No existing conversation found, this could be a personal channel or the main channel the integration was added to
            # find the bot integration for this main channel and use it to create a new conversation
            self.convo = Conversation.objects.get_or_create(
                slack_channel_id=self.bot_id,
                slack_user_id=self.user_id,
                slack_team_id=self._team_id,
                defaults=dict(
                    bot_integration=BotIntegration.objects.get(
                        slack_channel_id=self.bot_id,
                        slack_team_id=self._team_id,
                    ),
                ),
            )[0]

        fetch_missing_convo_metadata(self.convo)
        self._access_token = self.convo.bot_integration.slack_access_token

        if files:
            self._file = files[0]  # we only process the first file for now
            # Additional check required to access file info - https://api.slack.com/apis/channels-between-orgs#check_file_info
            if self._file.get("file_access") == "check_file_info":
                self._file = fetch_file_info(self._file["id"], self._access_token)
            self.input_type = self._file.get("mimetype", "").split("/")[0] or "unknown"
            if (
                self.input_type == "unknown"
                and self._file.get("subtype") == "slack_audio"
            ):
                self.input_type = "audio"
        else:
            self._file = None
            self.input_type = "text"

        if actions:
            self._actions = actions
            self.input_type = "interactive"
        else:
            self._actions = None

        super().__init__()

    def get_input_text(self) -> str | None:
        return self._text

    def get_input_audio(self) -> str | None:
        if not self._file:
            return None
        url = self._file.get("url_private_download")
        mime_type = self._file.get("mimetype") or mimetypes.guess_type(url)[0]
        if not (url and mime_type):
            return None
        assert "audio/" in mime_type or "video/" in mime_type, (
            f"Unsupported mime type {mime_type} for {url}"
        )
        # download file from slack
        r = requests.get(url, headers={"Authorization": f"Bearer {self._access_token}"})
        raise_for_status(r)
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

    def get_interactive_msg_info(self) -> ButtonPressed:
        return ButtonPressed(
            button_id=self._actions[0]["value"], context_msg_id=self._msg_ts
        )

    def send_run_status(
        self, update_msg_id: str | None, references: list[SearchReference] | None = None
    ) -> str | None:
        if not self.run_status:
            return update_msg_id
        return self.send_msg(text=self.run_status, update_msg_id=update_msg_id)

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
        text = text or "\u200b"  # handle empty text with zero-width space

        if self._read_rcpt_ts and self._read_rcpt_ts != self._msg_ts:
            delete_msg(
                channel=self.bot_id,
                thread_ts=self._read_rcpt_ts,
                token=self._access_token,
            )
            self._read_rcpt_ts = None

        if not self.can_update_message:
            update_msg_id = None
        self._msg_ts, num_splits = self.send_msg_to(
            text=text,
            audio=audio,
            video=video,
            buttons=buttons,
            channel=self.bot_id,
            channel_is_personal=self.convo.slack_channel_is_personal,
            username=self.convo.bot_integration.name,
            token=self._access_token,
            thread_ts=self._msg_ts,
            update_msg_ts=update_msg_id,
        )
        if num_splits > 1:
            self.can_update_message = False
        return self._msg_ts

    @classmethod
    def send_msg_to(
        cls,
        *,
        text: str | None = None,
        audio: list[str] | None = None,
        video: list[str] | None = None,
        buttons: list[ReplyButton] = None,
        documents: list[str] = None,
        ## whatsapp specific
        channel: str,
        channel_is_personal: bool,
        username: str,
        token: str,
        thread_ts: str = None,
        update_msg_ts: str = None,
    ) -> tuple[str | None, int]:
        splits = text_splitter(text, chunk_size=SLACK_MAX_SIZE, length_function=len)
        for doc in splits[:-1]:
            thread_ts = chat_post_message(
                text=doc.text,
                channel=channel,
                channel_is_personal=channel_is_personal,
                thread_ts=thread_ts,
                update_msg_ts=update_msg_ts,
                username=username,
                token=token,
            )
            update_msg_ts = None
        thread_ts = chat_post_message(
            text=splits[-1].text,
            audio=audio,
            video=video,
            buttons=buttons or [],
            channel=channel,
            channel_is_personal=channel_is_personal,
            thread_ts=thread_ts,
            update_msg_ts=update_msg_ts,
            username=username,
            token=token,
        )
        return thread_ts, len(splits)

    def mark_read(self):
        text = self.convo.bot_integration.slack_read_receipt_msg.strip()
        if not text:
            return
        text = self.translate_response(text)
        self._read_rcpt_ts = chat_post_message(
            text=text,
            channel=self.bot_id,
            channel_is_personal=self.convo.slack_channel_is_personal,
            thread_ts=self._msg_ts,
            token=self._access_token,
            username=self.convo.bot_integration.name,
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
        lambda user_id: fetch_user_info(user_id, token),
        data["members"],
        max_workers=10,
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
                slack_user_name=get_slack_user_name(user_data)
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


def get_slack_user_name(user: dict) -> str | None:
    return (
        user.get("real_name")
        or user.get("profile", {}).get("display_name")
        or user.get("name")
        or ""
    )


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


def fetch_file_info(file_id: str, token: str) -> dict[str, typing.Any]:
    res = requests.get(
        "https://slack.com/api/files.info",
        params={"file": file_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    data = parse_slack_response(res)
    return data["file"]


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
    user_name = get_slack_user_name(user)
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
    try:
        # set the topic and invite the user to the channel
        invite_user_to_channel(
            user_id=user_id,
            channel_id=channel_id,
            token=bi.slack_access_token,
        )
    except SlackAPIError as e:
        # skip if the user is restricted
        if e.error in [
            "user_is_ultra_restricted",
            "user_is_restricted",
            "user_team_not_in_channel",
        ]:
            return
        else:
            raise
    set_slack_channel_topic(
        bot_name=bi.name,
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
    update_msg_ts: str = None,
    channel_is_personal: bool = False,
    audio: list[str] | None = None,
    video: list[str] | None = None,
    username: str = "Video Bot",
    buttons: list[ReplyButton] = None,
) -> str | None:
    if buttons is None:
        buttons = []
    if channel_is_personal:
        # don't thread in personal channels
        thread_ts = None
    if update_msg_ts:
        res = requests.post(
            "https://slack.com/api/chat.update",
            json={
                "channel": channel,
                "ts": update_msg_ts,
                "text": text,
                "username": username,
                "icon_emoji": ":robot_face:",
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": text},
                    },
                    *create_file_block("Audio", token, audio),
                    *create_file_block("Video", token, video),
                    *create_button_block(buttons),
                ],
            },
            headers={
                "Authorization": f"Bearer {token}",
            },
        )
    else:
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
                    *create_file_block("Audio", token, audio),
                    *create_file_block("Video", token, video),
                    *create_button_block(buttons),
                ],
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
    urls: list[str] | None = None,
) -> list[dict]:
    if not urls:
        return []
    for url in urls:
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
        yield {
            "type": "file",
            "external_id": url,
            "source": "remote",
        }


def create_button_block(buttons: list[ReplyButton]) -> list[dict]:
    if not buttons:
        return []
    return [
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": button["title"]},
                    "value": button["id"],
                    "action_id": "button_" + button["id"],
                }
                for button in buttons
            ],
        }
    ]


def send_confirmation_msg(bot: BotIntegration):
    confirmation_msg = Template(SLACK_CONFIRMATION_MSG).safe_substitute(**vars(bot))
    res = requests.post(
        str(bot.slack_channel_hook_url),
        json={"text": confirmation_msg},
    )
    raise_for_status(res)


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
    raise_for_status(res)
    data = res.json()
    print(f"> {res.request.url.split('/')[-1]}: {data}")
    if data.get("ok"):
        return data
    else:
        raise SlackAPIError(data.get("error", data))


class SlackAPIError(Exception):
    def __init__(self, error: str | dict):
        self.error = error
        super().__init__(error)
