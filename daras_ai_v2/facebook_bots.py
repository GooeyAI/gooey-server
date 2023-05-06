import mimetypes
import typing

import requests

from bots.models import BotIntegration, Platform, Conversation
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import settings
from daras_ai_v2.all_pages import Workflow
from daras_ai_v2.base import BasePage

WHATSAPP_AUTH_HEADER = {
    "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
}


class BotInterface:
    input_message: dict
    platform: Platform
    billing_account_uid: str
    page_cls: typing.Type[BasePage] | None
    query_params: dict
    bot_id: str
    user_id: str
    input_type: str
    language: str
    show_feedback_buttons: bool = False
    convo: Conversation

    def send_msg(
        self,
        *,
        text: str = None,
        audio: str = None,
        video: str = None,
        buttons: list = None,
    ) -> str | None:
        raise NotImplementedError

    def mark_read(self):
        raise NotImplementedError

    def get_input_text(self) -> str | None:
        raise NotImplementedError

    def get_input_audio(self) -> str | None:
        raise NotImplementedError

    def get_input_video(self) -> str | None:
        raise NotImplementedError

    def nice_filename(self, mime_type: str) -> str:
        ext = mimetypes.guess_extension(mime_type) or ""
        return f"{self.platform}_{self.input_type}_from_{self.user_id}_to_{self.bot_id}{ext}"

    def _unpack_bot_integration(self, bi: BotIntegration):
        self.page_cls = Workflow(bi.saved_run.workflow).page_cls
        self.query_params = self.page_cls.clean_query_params(
            bi.saved_run.example_id, bi.saved_run.run_id, bi.saved_run.uid
        )
        self.billing_account_uid = bi.billing_account_uid
        self.language = bi.user_language
        self.show_feedback_buttons = bi.show_feedback_buttons


class WhatsappBot(BotInterface):
    def __init__(self, message: dict, metadata: dict):
        self.input_message = message
        self.platform = Platform.WHATSAPP

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
    ) -> str | None:
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


def send_wa_msg(
    *,
    bot_number: str,
    user_number: str,
    response_text: str,
    response_audio: str = None,
    response_video: str = None,
    buttons: list = None,
) -> str | None:
    if response_video:
        if buttons:
            messages = [
                # interactive text msg + video in header
                {
                    "body": {
                        "text": response_text,
                    },
                    "header": {
                        "type": "video",
                        "video": {"link": response_video},
                    },
                },
            ]
        else:
            messages = [
                # simple video msg + text caption
                {
                    "type": "video",
                    "video": {
                        "link": response_video,
                        "caption": response_text,
                    },
                },
            ]
    elif response_audio:
        if buttons:
            # audio can't be sent as an interaction, so send text and audio separately
            messages = [
                # simple audio msg
                {
                    "type": "audio",
                    "audio": {"link": response_audio},
                },
            ]
            send_wa_msgs_raw(
                bot_number=bot_number,
                user_number=user_number,
                messages=messages,
            )
            messages = [
                # interactive text msg
                {
                    "body": {
                        "text": response_text,
                    },
                },
            ]
        else:
            # audio doesn't support captions, so send text and audio separately
            messages = [
                # simple text msg
                {
                    "type": "text",
                    "text": {
                        "body": response_text,
                        "preview_url": True,
                    },
                },
                # simple audio msg
                {
                    "type": "audio",
                    "audio": {"link": response_audio},
                },
            ]
    else:
        # text message
        if buttons:
            messages = [
                # interactive text msg
                {
                    "body": {
                        "text": response_text,
                    }
                },
            ]
        else:
            messages = [
                # simple text msg
                {
                    "type": "text",
                    "text": {
                        "body": response_text,
                        "preview_url": True,
                    },
                },
            ]
    return send_wa_msgs_raw(
        bot_number=bot_number,
        user_number=user_number,
        messages=messages,
        buttons=buttons,
    )


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


def send_wa_msgs_raw(
    *, bot_number, user_number, messages: list, buttons: list = None
) -> str | None:
    msg_id = None
    for msg in messages:
        body = {
            "messaging_product": "whatsapp",
            "to": user_number,
            "preview_url": True,
        }
        if buttons:
            body |= {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    **msg,
                    "action": {"buttons": buttons},
                },
            }
        else:
            body |= msg
        r = requests.post(
            f"https://graph.facebook.com/v16.0/{bot_number}/messages",
            headers=WHATSAPP_AUTH_HEADER,
            json=body,
        )
        confirmation = r.json()
        print("send_wa_msgs_raw:", r.status_code, confirmation)
        msg_id = confirmation["messages"][0]["id"]
    return msg_id


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
            self.platform = Platform.INSTAGRAM
        else:
            self.platform = Platform.FACEBOOK

        self.input_message = messaging["message"]

        if "text" in self.input_message:
            self.input_type = "text"
        elif "attachments" in self.input_message:
            self.input_type = self.input_message["attachments"][0]["type"]
        else:
            self.input_type = "unknown"

        self.user_id = messaging["sender"]["id"]
        recipient_id = messaging["recipient"]["id"]
        if self.platform == Platform.INSTAGRAM:
            bi = BotIntegration.objects.get(ig_account_id=recipient_id)
            self.convo = Conversation.objects.get_or_create(
                bot_integration=bi,
                fb_page_id=self.user_id,
            )[0]
        else:
            bi = BotIntegration.objects.get(fb_page_id=recipient_id)
            self.convo = Conversation.objects.get_or_create(
                bot_integration=bi,
                fb_page_id=self.user_id,
                ig_account_id=self.user_id,
            )[0]
        self._unpack_bot_integration(bi)
        self.bot_id = bi.fb_page_id

        self._access_token = bi.fb_page_access_token

    def send_msg(
        self,
        *,
        text: str = None,
        audio: str = None,
        video: str = None,
        buttons: list = None,
    ):
        send_fb_msg(
            access_token=self._access_token,
            bot_id=self.bot_id,
            user_id=self.user_id,
            text=text,
            audio=audio,
            video=video,
        )

    def mark_read(self):
        if self.platform == Platform.INSTAGRAM:
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
        return self.input_message.get("text")

    def get_input_audio(self) -> str | None:
        url = (
            self.input_message.get("attachments", [{}])[0].get("payload", {}).get("url")
        )
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

    def get_input_video(self) -> str | None:
        raise NotImplementedError


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
