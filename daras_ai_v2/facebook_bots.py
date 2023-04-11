import mimetypes
import typing

import requests
from google.cloud import firestore

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import settings, db

WHATSAPP_AUTH_HEADER = {
    "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
}


class BotInterface:
    platform: db.BOT_PLATFORM_LITERAL
    billing_account_uid: str
    page_cls: typing.Type | None
    query_params: dict
    bot_id: str
    user_id: str
    input_type: str
    language: str

    def send_msg(self, *, text: str = None, audio: str = None, video: str = None):
        raise NotImplementedError

    def mark_read(self):
        raise NotImplementedError

    def get_input_text(self) -> str | None:
        raise NotImplementedError

    def get_input_audio(self) -> str | None:
        raise NotImplementedError

    def nice_filename(self, mime_type: str) -> str:
        ext = mimetypes.guess_extension(mime_type) or ""
        return f"{self.platform}_{self.input_type}_from_{self.user_id}_to_{self.bot_id}{ext}"

    def unpack_fb_page_snapshot(
        self, snapshot: firestore.DocumentSnapshot | None
    ) -> dict:
        if not (snapshot and snapshot.exists):
            raise ValueError(f"Bot {self.bot_id} not found")
        fb_page = snapshot.to_dict()

        from server import page_map, normalize_slug

        self.query_params = fb_page.get("connected_query_params") or {}
        self.billing_account_uid = fb_page["uid"]

        self.language = fb_page.get("language", "en")

        page_slug = fb_page.get("connected_page_slug")
        if page_slug:
            page_slug = normalize_slug(page_slug)
        try:
            self.page_cls = page_map[page_slug]
        except KeyError:
            self.page_cls = None

        return fb_page


class WhatsappBot(BotInterface):
    def __init__(self, message: dict, metadata: dict):
        self._message = message
        self.platform = "wa"

        self.bot_id = metadata["phone_number_id"]
        self.user_id = message["from"]

        self.input_type = message["type"]

        snapshot = db.get_connected_bot_page_ref("wa", self.bot_id).get()
        self.unpack_fb_page_snapshot(snapshot)

    def get_input_text(self) -> str | None:
        try:
            return self._message["text"]["body"]
        except KeyError:
            return None

    def get_input_audio(self) -> str | None:
        try:
            media_id = self._message["audio"]["id"]
        except KeyError:
            return None
        # download file from whatsapp
        content, mime_type = retrieve_wa_media_by_id(media_id)
        # upload file to firebase
        audio_url = upload_file_from_bytes(
            filename=self.nice_filename(mime_type),
            data=content,
            content_type=mime_type,
        )
        return audio_url

    def send_msg(self, *, text: str = None, audio: str = None, video: str = None):
        send_wa_msg(
            bot_number=self.bot_id,
            user_number=self.user_id,
            response_text=text,
            response_audio=audio,
            response_video=video,
        )

    def mark_read(self):
        wa_mark_read(self.bot_id, self._message["id"])


def send_wa_msg(
    *,
    bot_number: str,
    user_number: str,
    response_text: str,
    response_audio: str = None,
    response_video: str = None,
):
    if response_video:
        # video message with caption
        messages = [
            {
                "type": "video",
                "video": {"link": response_video, "caption": response_text},
            },
        ]
    elif response_audio:
        # audio doesn't support captions, so send text and audio separately
        messages = [
            {"type": "text", "text": {"body": response_text}},
            {"type": "audio", "audio": {"link": response_audio}},
        ]
    else:
        # text message
        messages = [
            {"type": "text", "text": {"body": response_text}},
        ]
    send_wa_msgs_raw(bot_number=bot_number, user_number=user_number, messages=messages)


def retrieve_wa_media_by_id(media_id: str) -> (bytes, str):
    # get media info
    r1 = requests.get(
        f"https://graph.facebook.com/v16.0/{media_id}/",
        headers=WHATSAPP_AUTH_HEADER,
    )
    r1.raise_for_status()
    media_info = r1.json()
    # download media
    r2 = requests.get(
        media_info["url"],
        headers=WHATSAPP_AUTH_HEADER,
    )
    r2.raise_for_status()
    content = r2.content
    # return content and mime type
    return content, media_info["mime_type"]


def send_wa_msgs_raw(*, bot_number, user_number, messages: list):
    for msg in messages:
        r = requests.post(
            f"https://graph.facebook.com/v16.0/{bot_number}/messages",
            headers=WHATSAPP_AUTH_HEADER,
            json={
                "messaging_product": "whatsapp",
                "to": user_number,
                **msg,
            },
        )
        print("send_wa_msgs_raw:", r.status_code, r.json())


def wa_mark_read(bot_number: str, message_id: str):
    # send read receipt
    r = requests.post(
        f"https://graph.facebook.com/v16.0/{bot_number}/messages",
        headers=WHATSAPP_AUTH_HEADER,
        json={
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        },
    )
    print("wa_mark_read:", r.status_code, r.json())


class FacebookBot(BotInterface):
    def __init__(self, object_name: str, messaging: dict):
        if object_name == "instagram":
            self.platform = "ig"
        else:
            self.platform = "fb"

        self._message = messaging["message"]

        if "text" in self._message:
            self.input_type = "text"
        elif "attachments" in self._message:
            self.input_type = self._message["attachments"][0]["type"]
        else:
            self.input_type = "unknown"

        self.user_id = messaging["sender"]["id"]
        self.bot_id, snapshot = _resolve_fb_page(self.platform, messaging)

        fb_page = self.unpack_fb_page_snapshot(snapshot)
        self._access_token = fb_page.get("page_access_token")

    def send_msg(self, *, text: str = None, audio: str = None, video: str = None):
        send_fb_msg(
            access_token=self._access_token,
            bot_id=self.bot_id,
            user_id=self.user_id,
            text=text,
            audio=audio,
            video=video,
        )

    def mark_read(self):
        if self.platform == "ig":
            # instagram doesn't support read receipts :(
            return
        send_fb_msgs_raw(
            access_token=self._access_token,
            page_id=self.bot_id,
            recipient_id=self.user_id,
            messages=[
                {"sender_action": "mark_seen"},
                {"sender_action": "typing_on"},
            ],
        )

    def get_input_text(self) -> str | None:
        return self._message.get("text")

    def get_input_audio(self) -> str | None:
        url = self._message.get("attachments", [{}])[0].get("payload", {}).get("url")
        if not url:
            return None
        # downlad file from facebook
        r = requests.get(url)
        r.raise_for_status()
        mime_type = r.headers["content-type"]
        # upload file to firebase
        audio_url = upload_file_from_bytes(
            filename=self.nice_filename(mime_type),
            data=r.content,
            content_type=mime_type,
        )
        return audio_url


def _resolve_fb_page(
    platform: db.BOT_PLATFORM_LITERAL, messaging: dict
) -> (str, firestore.DocumentSnapshot | None):
    page_id = messaging["recipient"]["id"]
    snapshot = None
    if platform == "ig":
        # need to resolve the facebook page connected to this instagram page
        try:
            snapshot = list(
                db.get_collection_ref(db.CONNECTED_BOTS_COLLECTION)
                .where("ig_account_id", "==", page_id)
                .limit(1)
                .get()
            )[0]
            page_id = snapshot.id.split(":")[1]
        except IndexError:
            # if ig page is not saved in db, ignore
            pass
    else:
        snapshot = db.get_connected_bot_page_ref("fb", page_id).get()
    return page_id, snapshot


def send_fb_msg(
    *,
    access_token: str,
    bot_id: str,
    user_id: str,
    text: str = None,
    audio: str = None,
    video: str = None,
):
    messages = []
    if text:
        messages.append(
            {
                "messaging_type": "RESPONSE",
                "message": {"text": text},
            },
        )
    # either audio or video should be sent, not both
    if video:
        messages.append(
            {
                "messaging_type": "RESPONSE",
                "message": {
                    "attachment": {"type": "video", "payload": {"url": video}},
                },
            },
        )
    elif audio:
        messages.append(
            {
                "messaging_type": "RESPONSE",
                "message": {
                    "attachment": {"type": "audio", "payload": {"url": audio}},
                },
            },
        )
    # send the response to the user
    send_fb_msgs_raw(
        page_id=bot_id,
        access_token=access_token,
        recipient_id=user_id,
        messages=messages,
    )


def send_fb_msgs_raw(
    *,
    page_id: str,
    access_token: str,
    recipient_id: str,
    messages: list,
):
    for data in messages:
        r = requests.post(
            f"https://graph.facebook.com/v15.0/{page_id}/messages",
            json={
                "access_token": access_token,
                "recipient": {"id": recipient_id},
                **data,
            },
        )
        print("send_fb_msgs_raw:", r.status_code, r.json())
