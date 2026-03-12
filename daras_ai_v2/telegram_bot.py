import requests
from loguru import logger
from bots.models import BotIntegration, Conversation, Platform
from daras_ai.image_input import get_mimetype_from_response, upload_file_from_bytes
from daras_ai_v2.asr import audio_bytes_to_wav
from daras_ai_v2.bots import BotInterface, BotIntegrationLookupFailed, ButtonPressed
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.language_model import ConversationEntry
from daras_ai_v2.search_ref import SearchReference
from daras_ai_v2.text_splitter import text_splitter
from recipes.VideoBots import ReplyButton

TELEGRAM_MAX_MSG_LENGTH = 4096
TELEGRAM_MAX_CALLBACK_DATA = 64
TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramBot(BotInterface):
    platform = Platform.TELEGRAM
    can_update_message = True

    def __init__(self, *, bot_id: str, data: dict):
        if "callback_query" in data:
            callback = data["callback_query"]
            self._chat_id = str(callback["message"]["chat"]["id"])
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

        if not self.convo.telegram_user_name and user_name:
            Conversation.objects.filter(pk=self.convo.pk).update(
                telegram_user_name=user_name,
            )

        super().__init__()

    def get_input_text(self) -> str | None:
        return self._text

    def get_input_audio(self) -> str | None:
        voice = self._message.get("voice")
        audio = self._message.get("audio")
        file_obj = voice or audio
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
        splits = text_splitter(
            text, chunk_size=TELEGRAM_MAX_MSG_LENGTH, length_function=len
        )

        msg_id = update_msg_id
        for i, doc in enumerate(splits):
            is_last = i == len(splits) - 1
            chunk_markup = reply_markup if is_last else None
            if msg_id and self.can_update_message:
                msg_id = _edit_message(
                    self._bot_token,
                    chat_id=self._chat_id,
                    message_id=msg_id,
                    text=doc.text,
                    reply_markup=chunk_markup,
                )
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


def _tg_api_call(bot_token: str, method: str, data: dict) -> dict:
    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/{method}"
    r = requests.post(url, json=data)
    raise_for_status(r)
    return r.json().get("result", {})


def _send_text_message(
    bot_token: str,
    *,
    chat_id: str,
    text: str,
    reply_markup: dict | None = None,
) -> str | None:
    data = dict(chat_id=chat_id, text=text, parse_mode="HTML")
    if reply_markup:
        data["reply_markup"] = reply_markup
    try:
        result = _tg_api_call(bot_token, "sendMessage", data)
    except requests.exceptions.HTTPError:
        data.pop("parse_mode", None)
        result = _tg_api_call(bot_token, "sendMessage", data)
    return str(result.get("message_id", ""))


def _edit_message(
    bot_token: str,
    *,
    chat_id: str,
    message_id: str,
    text: str,
    reply_markup: dict | None = None,
) -> str | None:
    data = dict(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        parse_mode="HTML",
    )
    if reply_markup:
        data["reply_markup"] = reply_markup
    try:
        result = _tg_api_call(bot_token, "editMessageText", data)
    except requests.exceptions.HTTPError as e:
        if "message is not modified" in str(e):
            return message_id
        data.pop("parse_mode", None)
        try:
            result = _tg_api_call(bot_token, "editMessageText", data)
        except requests.exceptions.HTTPError as e2:
            if "message is not modified" in str(e2):
                return message_id
            raise
    return str(result.get("message_id", message_id))


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
    download_url = f"{TELEGRAM_API_BASE}/file/bot{bot_token}/{file_path}"
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
