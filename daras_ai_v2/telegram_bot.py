import re
import secrets

import aifail
import requests
from furl import furl
from loguru import logger

from bots.models import BotIntegration, Conversation, Platform
from daras_ai.image_input import get_mimetype_from_response, upload_file_from_bytes
from daras_ai.text_format import unmarkdown
from daras_ai_v2.asr import audio_bytes_to_wav
from daras_ai_v2.base import RecipeRunState
from daras_ai_v2.bots import BotInterface, BotIntegrationLookupFailed, ButtonPressed
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.language_model import ConversationEntry
from daras_ai_v2.search_ref import SearchReference
from daras_ai_v2.telegram_markdown_renderer import markdown_to_telegram_html
from daras_ai_v2.text_splitter import text_splitter
from recipes.VideoBots import ReplyButton

TELEGRAM_MAX_MSG_LENGTH = 4096
TELEGRAM_MAX_CALLBACK_DATA = 64
TELEGRAM_API_BASE = "https://api.telegram.org"
TELEGRAM_DRAFT_MSG_ID = "draft"
TELEGRAM_DEFAULT_COMMANDS = [
    {
        "command": "new",
        "description": "Start a new conversation",
    }
]


class TelegramBot(BotInterface):
    platform = Platform.TELEGRAM
    can_update_message = True

    _is_private_chat: bool = False

    def __init__(self, *, bot_id: str, data: dict):
        if "callback_query" in data:
            callback = data["callback_query"]
            self._chat_id = str(callback["message"]["chat"]["id"])
            self._is_private_chat = callback["message"]["chat"]["type"] == "private"
            self._callback_query_id = callback["id"]
            self._callback_data = callback["data"]
            self._callback_context_msg_id = str(callback["message"]["message_id"])
            self._from_user = callback["from"]
            self.user_msg_id = str(callback["id"])
            self.input_type = "interactive"
            self._text = ""
            self._message = callback.get("message", {})
        elif "message" in data:
            message = data["message"]
            self._chat_id = str(message["chat"]["id"])
            self._is_private_chat = message["chat"]["type"] == "private"
            self._callback_query_id = None
            self._from_user = message["from"]
            self.user_msg_id = str(message["message_id"])
            self._text = message.get("text") or message.get("caption") or ""
            self._message = message
            self.input_type = _detect_input_type(message)
        else:
            raise ValueError(f"Unsupported Telegram update: {data.keys()}")

        self.bot_id = bot_id
        self.user_id = str(self._from_user["id"])

        try:
            bi = BotIntegration.objects.get(telegram_bot_id=bot_id)
        except BotIntegration.DoesNotExist:
            raise BotIntegrationLookupFailed(
                "This bot is not connected to any Gooey.AI workflow."
            )

        self._bot_token = bi.telegram_bot_token

        user_name = self._from_user.get("username", "")
        self.convo = Conversation.objects.get_or_create(
            bot_integration=bi,
            telegram_user_id=self.user_id,
            defaults=dict(telegram_user_name=user_name),
        )[0]

        if self.convo.telegram_user_name != user_name:
            Conversation.objects.filter(pk=self.convo.pk).update(
                telegram_user_name=user_name,
            )
            self.convo.telegram_user_name = user_name

        self._stream_draft_id: int | None = None
        super().__init__()

    def get_input_text(self) -> str | None:
        return self._text

    def get_input_audio(self) -> str | None:
        file_obj = (
            self._message.get("voice")
            or self._message.get("audio")
            or self._message.get("video")
            or self._message.get("video_note")
        )
        if not file_obj:
            return None
        file_id = file_obj["file_id"]
        data, mime_type = _download_telegram_file(self._bot_token, file_id)
        data, _ = audio_bytes_to_wav(data)
        mime_type = "audio/wav"
        return upload_file_from_bytes(
            filename=self.nice_filename(mime_type),
            data=data,
            content_type=mime_type,
        )

    def get_input_images(self) -> list[str] | None:
        photos = self._message.get("photo")
        if not photos:
            return None
        best_photo = max(photos, key=lambda p: p.get("file_size", 0))
        data, mime_type = _download_telegram_file(
            self._bot_token, best_photo["file_id"]
        )
        url = upload_file_from_bytes(
            filename=self.nice_filename(mime_type or "image/jpeg"),
            data=data,
            content_type=mime_type or "image/jpeg",
        )
        return [url]

    def get_input_documents(self) -> list[str] | None:
        doc = self._message.get("document")
        if not doc:
            return None
        data, mime_type = _download_telegram_file(self._bot_token, doc["file_id"])
        url = upload_file_from_bytes(
            filename=doc.get("file_name")
            or self.nice_filename(mime_type or "application/octet-stream"),
            data=data,
            content_type=mime_type or "application/octet-stream",
        )
        return [url]

    def get_location_info(self) -> dict | None:
        location = self._message.get("location")
        if not location:
            return None
        return {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
        }

    def get_interactive_msg_info(self) -> ButtonPressed:
        _tg_api_call(
            self._bot_token,
            "answerCallbackQuery",
            data=dict(callback_query_id=self._callback_query_id),
        )
        return ButtonPressed(
            button_id=self._callback_data,
            context_msg_id=self._callback_context_msg_id,
        )

    def send_run_status(
        self,
        update_msg_id: str | None = None,
        references: list[SearchReference] | None = None,
        prompt_delta: dict[int, ConversationEntry] | None = None,
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
        reply_markup = _build_inline_keyboard(buttons) if buttons else None

        for url in audio or []:
            _tg_api_call(
                self._bot_token,
                "sendAudio",
                data=dict(chat_id=self._chat_id, audio=url),
            )

        for url in video or []:
            _tg_api_call(
                self._bot_token,
                "sendVideo",
                data=dict(chat_id=self._chat_id, video=url),
            )

        for url in documents or []:
            _tg_api_call(
                self._bot_token,
                "sendDocument",
                data=dict(chat_id=self._chat_id, document=url),
            )

        if not text and not reply_markup:
            return update_msg_id

        text = text or "\u200b"

        use_draft_msg = (
            self.recipe_run_state == RecipeRunState.running
            and self._is_private_chat
            and self.streaming_enabled
            and not reply_markup
            and not (audio or video or documents)
        )
        if use_draft_msg:
            if self._stream_draft_id is None:
                self._stream_draft_id = secrets.randbelow(90_000) + 1
            _send_message_draft(
                self._bot_token,
                chat_id=self._chat_id,
                draft_id=self._stream_draft_id,
                text=text[:TELEGRAM_MAX_MSG_LENGTH],
            )
            return TELEGRAM_DRAFT_MSG_ID

        if update_msg_id == TELEGRAM_DRAFT_MSG_ID:
            update_msg_id = None

        splits = text_splitter(
            text, chunk_size=TELEGRAM_MAX_MSG_LENGTH, length_function=len
        )

        msg_id = update_msg_id
        for i, doc in enumerate(splits):
            is_last = i == len(splits) - 1
            chunk_markup = reply_markup if is_last else None
            if (
                i == 0
                and msg_id
                and self.can_update_message
                and len(doc.text) <= TELEGRAM_MAX_MSG_LENGTH
            ):
                msg_id = _edit_message(
                    self._bot_token,
                    chat_id=self._chat_id,
                    message_id=msg_id,
                    text=doc.text,
                    reply_markup=chunk_markup,
                )
                if len(splits) > 1:
                    self.can_update_message = False
            else:
                msg_id = _send_text_message(
                    self._bot_token,
                    chat_id=self._chat_id,
                    text=doc.text,
                    reply_markup=chunk_markup,
                )

        if len(splits) > 1:
            self.can_update_message = False

        return msg_id

    def mark_read(self):
        _tg_api_call(
            self._bot_token,
            "sendChatAction",
            data=dict(chat_id=self._chat_id, action="typing"),
        )


def _detect_input_type(message: dict) -> str:
    if message.get("voice") or message.get("audio"):
        return "audio"
    if message.get("video") or message.get("video_note"):
        return "video"
    if message.get("photo"):
        return "image"
    if message.get("document"):
        return "document"
    if message.get("location"):
        return "location"
    return "text"


def _send_text_message(
    bot_token: str,
    *,
    chat_id: str,
    text: str,
    reply_markup: dict | None = None,
) -> str | None:
    data = dict(chat_id=chat_id, text=text)
    if reply_markup:
        data["reply_markup"] = reply_markup
    result = _tg_html_api_send_msg(bot_token, "sendMessage", data)
    return str(result.get("message_id", ""))


def _edit_message(
    bot_token: str,
    *,
    chat_id: str,
    message_id: str,
    text: str,
    reply_markup: dict | None = None,
) -> str | None:
    data = dict(chat_id=chat_id, message_id=message_id, text=text)
    if reply_markup:
        data["reply_markup"] = reply_markup
    try:
        result = _tg_html_api_send_msg(bot_token, "editMessageText", data)
    except requests.exceptions.HTTPError as e:
        if "message is not modified" in str(e):
            return message_id
        else:
            raise
    return str(result.get("message_id", message_id))


def _send_message_draft(
    bot_token: str,
    *,
    chat_id: str,
    draft_id: int,
    text: str,
) -> None:
    data = dict(chat_id=chat_id, draft_id=draft_id, text=text)
    _tg_html_api_send_msg(bot_token, "sendMessageDraft", data)


def _build_inline_keyboard(
    buttons: list[ReplyButton] | None,
) -> dict | None:
    if not buttons:
        return None
    keyboard = []
    for btn in buttons:
        callback_data = btn.get("id") or btn.get("title") or ""
        encoded = callback_data.encode("utf-8")
        if len(encoded) > TELEGRAM_MAX_CALLBACK_DATA:
            callback_data = encoded[:TELEGRAM_MAX_CALLBACK_DATA].decode(
                "utf-8", errors="ignore"
            )
        keyboard.append(
            [
                dict(
                    text=btn.get("title") or btn.get("id") or "?",
                    callback_data=callback_data,
                )
            ]
        )
    return dict(inline_keyboard=keyboard)


def _download_telegram_file(bot_token: str, file_id: str) -> tuple[bytes, str]:
    result = _tg_api_call(bot_token, "getFile", data=dict(file_id=file_id))
    file_path = result["file_path"]
    download_url = (
        furl(TELEGRAM_API_BASE) / "file" / f"bot{bot_token}" / file_path
    ).url
    r = requests.get(download_url)
    raise_for_status(r)
    mime_type = get_mimetype_from_response(r)
    return r.content, mime_type


def get_telegram_bot_info(bot_token: str) -> dict:
    return _tg_api_call(bot_token, "getMe", data={})


def set_telegram_webhook(
    bot_token: str,
    webhook_url: str,
    secret_token: str | None = None,
) -> dict:
    data = dict(url=webhook_url, allowed_updates=["message", "callback_query"])
    if secret_token:
        data["secret_token"] = secret_token
    result = _tg_api_call(bot_token, "setWebhook", data)
    return result


def set_telegram_commands(
    bot_token: str,
    commands: list[dict[str, str]] | None = None,
) -> dict:
    data = dict(commands=commands or TELEGRAM_DEFAULT_COMMANDS)
    result = _tg_api_call(bot_token, "setMyCommands", data)
    return result


TELEGRAM_PARSE_ERR_RE = re.compile(
    r"can't parse entities|parse entities|find end of the entity", re.IGNORECASE
)


def _tg_html_api_send_msg(
    bot_token: str,
    endpoint: str,
    data: dict,
    *,
    timeout: float = 1,  # HACK: sometimes the telegram api blocks if no timeout is set
):
    text = data.get("text")
    html_data = data | dict(text=markdown_to_telegram_html(text), parse_mode="HTML")
    try:
        return _tg_api_call(bot_token, endpoint, html_data, timeout=timeout)
    except requests.exceptions.HTTPError as e:
        if TELEGRAM_PARSE_ERR_RE.search(str(e)):
            logger.warning(f"{endpoint} failed, will retry without parse_mode {e=}")
            plain_text_data = data | dict(text=unmarkdown(text))
            return _tg_api_call(bot_token, endpoint, plain_text_data, timeout=timeout)
        else:
            raise


@aifail.retry_if(aifail.http_should_retry)
def _tg_api_call(
    bot_token: str, endpoint: str, data: dict, *, timeout: float | None = None
) -> dict:
    logger.debug(f"/{endpoint} {data=}")
    url = (furl(TELEGRAM_API_BASE) / f"bot{bot_token}" / endpoint).url
    try:
        response = requests.post(url, json=data, timeout=timeout)
    except requests.Timeout:
        if timeout:
            # try without timeout, just for making sure we weren't too conservative
            response = requests.post(url, json=data)
        else:
            raise
    raise_for_status(response)
    res = response.json()
    logger.debug(f"/{endpoint} {response.status_code=} {res=}")
    return res.get("result", {})
