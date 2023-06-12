import json
import uuid

import httpx
from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates

from daras_ai_v2 import settings

router = APIRouter()

templates = Jinja2Templates(directory="templates")


@router.post("/__/talkjs/webhook/")
async def talkjs_webhook(request: Request):
    body_json = await request.json()
    print(body_json)
    match body_json["type"]:
        case "message.sent":
            data = body_json["data"]
            conversation_id = data["conversation"]["id"]
            message = data["message"]
            sender_id = data["sender"]["id"]
            text = message["text"]

            if sender_id.startswith("bot"):
                return

            participants = data["conversation"]["participants"]
            participants.pop(sender_id, None)
            recipient_id = next(iter(participants.keys()))

            response_text = "hello world!" + text
            response_video = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d8a021ca-91c9-11ed-bbf6-02420a00015c/gooey.ai%20lipsync%20-%2052b62bff-de40-4a26-a499-4ab5dbac7d5a201.mp4"

            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"https://api.talkjs.com/v1/{settings.TALK_JS_APP_ID}/conversations/{conversation_id}/messages",
                    headers={
                        "Authorization": "Bearer " + settings.TALK_JS_SECRET_KEY,
                    },
                    json=[
                        {
                            "text": response_text,
                            "sender": recipient_id,
                            "type": "UserMessage",
                            # 'referencedMessageId': string
                            # custom?: { [key: string]: string }
                            "idempotencyKey": str(uuid.uuid1()),
                        },
                    ],
                )
                r.raise_for_status()

                r = await client.get(response_video)
                r.raise_for_status()

                filename = "out.mp4"
                r = await client.post(
                    f"https://api.talkjs.com/v1/{settings.TALK_JS_APP_ID}/files",
                    headers={
                        "Authorization": "Bearer " + settings.TALK_JS_SECRET_KEY,
                    },
                    files={"file": (filename, r.content)},
                )
                r.raise_for_status()
                attachment_token = r.json()["attachmentToken"]

                r = await client.post(
                    f"https://api.talkjs.com/v1/{settings.TALK_JS_APP_ID}/conversations/{conversation_id}/messages",
                    headers={
                        "Authorization": "Bearer " + settings.TALK_JS_SECRET_KEY,
                    },
                    json=[
                        {
                            "attachmentToken": attachment_token,
                            "sender": recipient_id,
                            "type": "UserMessage",
                            # 'referencedMessageId': string
                            # custom?: { [key: string]: string }
                            "idempotencyKey": str(uuid.uuid1()),
                        },
                    ],
                )
                r.raise_for_status()
