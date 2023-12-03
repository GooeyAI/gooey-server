import requests

from bots.models import BotIntegration, Platform, Conversation
from daras_ai.image_input import upload_file_from_bytes, get_mimetype_from_response
from daras_ai_v2 import settings
from daras_ai_v2.asr import run_google_translate, audio_bytes_to_wav
from daras_ai_v2.text_splitter import text_splitter
from daras_ai_v2.bots import BotInterface

WA_MSG_MAX_SIZE = 1024

WHATSAPP_AUTH_HEADER = {
    "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
}


class WhatsappBot(BotInterface):
    platform = Platform.WHATSAPP

    def __init__(self, message: dict, metadata: dict):
        self.input_message = message
        self.platform = Platform.WHATSAPP

        self.bot_id = metadata["phone_number_id"]  # this is NOT the phone number
        self.user_id = message["from"]  # this is a phone number

        self.input_type = message["type"]

        # if the message has a caption, treat it as text
        caption = self._get_caption()
        if caption:
            self.input_type = "text"
            self.input_message["text"] = {"body": caption}

        bi = BotIntegration.objects.get(wa_phone_number_id=self.bot_id)
        self.convo = Conversation.objects.get_or_create(
            bot_integration=bi,
            wa_phone_number="+" + self.user_id,
        )[0]
        self._unpack_bot_integration()

    def get_input_text(self) -> str | None:
        try:
            return self.input_message["text"]["body"]
        except KeyError:
            return None

    def _get_caption(self):
        return self.input_message.get(self.input_type, {}).get("caption")

    def get_input_audio(self) -> str | None:
        try:
            media_id = self.input_message["audio"]["id"]
        except KeyError:
            try:
                media_id = self.input_message["video"]["id"]
            except KeyError:
                return None
        return self._download_wa_media(media_id)

    def _download_wa_media(self, media_id: str) -> str:
        # download file from whatsapp
        data, mime_type = retrieve_wa_media_by_id(media_id)
        data, _ = audio_bytes_to_wav(data)
        mime_type = "audio/wav"
        # upload file to firebase
        return upload_file_from_bytes(
            filename=self.nice_filename(mime_type),
            data=data,
            content_type=mime_type,
        )

    def get_interactive_msg_info(self) -> tuple[str, str]:
        button_id = self.input_message["interactive"]["button_reply"]["id"]
        context_msg_id = self.input_message["context"]["id"]
        return button_id, context_msg_id

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
            text = run_google_translate(
                [text], self.language, glossary_url=self.output_glossary
            )[0]
        return send_wa_msg(
            bot_number=self.bot_id,
            user_number=self.user_id,
            response_text=text,
            response_audio=audio,
            response_video=video,
            buttons=buttons,
        )

    @classmethod
    def broadcast(
        cls,
        *,
        bi: BotIntegration,
        text: str = "",
        audio: str | None = None,
        video: str | None = None,
        buttons: list | None = None,
        convo_filter_kwargs: dict | None = None,
    ):
        from daras_ai_v2.bots import save_broadcast_messages

        ids = []
        convos = Conversation.objects.filter(
            bot_integration=bi, **(convo_filter_kwargs or {})
        )
        for convo in convos:
            id = send_wa_msg(
                bot_number=bi.wa_phone_number_id,
                user_number=convo.wa_phone_number,
                response_text=text,
                response_audio=audio,
                response_video=video,
                buttons=buttons,
            )
            ids += [id]

        # save the message in the background so we can return immediately from the api call
        save_broadcast_messages.delay(
            convos,
            text,
            ids,
        )

        return ", ".join(ids)

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
    # split text into chunks if too long
    if len(response_text) > WA_MSG_MAX_SIZE:
        splits = text_splitter(
            response_text, chunk_size=WA_MSG_MAX_SIZE, length_function=len
        )
        # preserve last chunk for later
        response_text = splits[-1].text
        # send all but last chunk
        send_wa_msgs_raw(
            bot_number=bot_number,
            user_number=user_number,
            messages=[
                # simple text msg
                {
                    "type": "text",
                    "text": {
                        "body": doc.text,
                        "preview_url": True,
                    },
                }
                for doc in splits[:-1]
            ],
        )

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
        r.raise_for_status()
        try:
            msg_id = confirmation["messages"][0]["id"]
        except (KeyError, IndexError):
            pass
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
        self._unpack_bot_integration()
        self.bot_id = bi.fb_page_id

        self._access_token = bi.fb_page_access_token

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
            text = run_google_translate(
                [text], self.language, glossary_url=self.output_glossary
            )[0]
        return send_fb_msg(
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
