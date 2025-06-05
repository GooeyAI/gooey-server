from __future__ import annotations

import json
import threading
import typing
from datetime import datetime

from django.core.exceptions import ValidationError
from furl import furl
from loguru import logger
from sentry_sdk import capture_exception
from twilio.base.exceptions import TwilioRestException
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import ClientConnection

from bots.models import BotIntegration
from functions.recipe_functions import LLMTool
from .language_model_openai_ws_tools import send_json, recv_json


# adapted from: https://github.com/openai/openai-realtime-twilio-demo/blob/main/websocket-server/src/sessionManager.ts
class RealtimeSession:
    def __init__(
        self,
        twilio_ws: ClientConnection,
        openai_ws: ClientConnection,
        tools: list[LLMTool] | None = None,
        audio_url: str | None = None,
    ):
        self.twilio_ws = twilio_ws
        self.openai_ws = openai_ws
        self.tools = tools

        self.audio_url = audio_url
        self.bi_id = furl(audio_url).args.get("bi_id")

        self.stream_sid: str | None = None
        self.call_sid: str | None = None
        self.last_assistant_item_id: str | None = None
        self.response_start_ts: int | None = None
        self.latest_media_ts: int = 0

        # transcript
        self.entry = {"role": "assistant", "content": "", "chunk": ""}

    def stream(self):
        while not (self.stream_sid and self.call_sid):
            msg = recv_json(self.twilio_ws)
            self.stream_sid = msg.get("streamSid")
            start_data = msg.get("start") or {}
            self.call_sid = start_data.get("callSid")

        threading.Thread(target=self.pipe_twilio_audio_to_openai).start()

        dispatch = {
            "input_audio_buffer.speech_started": self.on_speech_started,
            "response.audio.delta": self.on_audio_delta,
            "conversation.item.input_audio_transcription.completed": self.on_transcription_completed,
            "response.output_item.done": self.on_output_item_done,
        }
        try:
            while True:
                event = recv_json(self.openai_ws)
                handler = dispatch.get(event.get("type"))
                if not handler:
                    continue
                handler(event)
        except (ConnectionClosed, CallTransferred):
            pass

        yield self.entry

    def on_speech_started(self, _):
        if not (self.last_assistant_item_id and self.response_start_ts):
            return
        ## supposed to truncate the conversation, but it's not working?
        # send_json(
        #     self.openai_ws,
        #     {
        #         "type": "conversation.item.truncate",
        #         "item_id": self.last_assistant_item_id,
        #         "content_index": 0,
        #         "audio_end_ms": max(
        #             self.latest_media_ts - self.response_start_ts, 0
        #         ),
        #     },
        # )
        send_json(
            self.twilio_ws,
            {"event": "clear", "streamSid": self.stream_sid},
        )
        self.last_assistant_item_id = None
        self.response_start_ts = None

    def on_audio_delta(self, event: dict):
        if self.response_start_ts is None:
            self.response_start_ts = self.latest_media_ts
        item_id = event.get("item_id")
        if item_id:
            self.last_assistant_item_id = item_id
        send_json(
            self.twilio_ws,
            {
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {"payload": event["delta"]},
            },
        )
        send_json(
            self.twilio_ws,
            {"event": "mark", "streamSid": self.stream_sid},
        )

    def on_transcription_completed(self, event: dict):
        transcript = event.get("transcript")
        if not transcript:
            return
        self.append_transcription_entry("user", transcript)

    def on_output_item_done(self, event: dict):
        from recipes.VideoBots import exec_tool_call

        item = event.get("item")
        if not item:
            return

        content = item.get("content")
        if content:
            # Extract transcript from item content if available
            transcript = content[0].get("transcript") or ""
            if transcript:
                self.append_transcription_entry("assistant", transcript)
            if self.bi_id:
                handle_transfer_call_button(
                    content, self.openai_ws, self.call_sid, self.bi_id
                )

        # Handle function calls
        if self.tools and item.get("type") == "function_call":
            result = yield_from(
                exec_tool_call(
                    {"function": item},
                    {tool.name: tool for tool in self.tools},
                )
            )
            send_json(
                self.openai_ws,
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": item["call_id"],
                        "output": json.dumps(result),
                    },
                },
            )
            send_json(self.openai_ws, {"type": "response.create"})

    def pipe_twilio_audio_to_openai(self):
        try:
            while True:
                msg = recv_json(self.twilio_ws)
                match msg.get("event"):
                    case "stop":
                        break
                    case "media":
                        media = msg.get("media")
                        if not media:
                            continue
                        self.latest_media_ts = int(media["timestamp"])
                        send_json(
                            self.openai_ws,
                            {
                                "type": "input_audio_buffer.append",
                                "audio": media["payload"],
                            },
                        )
        except ConnectionClosed:
            pass
        finally:
            self.openai_ws.close()

    _first_transcript_ts: datetime | None = None
    _last_transcript_role: str | None = None

    def append_transcription_entry(self, role: str, content: str):
        content = content.strip()
        if not content:
            return
        if self._first_transcript_ts is None:
            self._first_transcript_ts = datetime.now()
        if self._last_transcript_role == role:
            line = "\n" + content
        else:
            self._last_transcript_role = role
            elapsed = datetime.now() - self._first_transcript_ts
            minutes, seconds = divmod(elapsed.total_seconds(), 60)
            formatted_time = f"[{minutes:02.0f}:{seconds:02.0f}]"
            line = f"\n\n{formatted_time} {role.title()}: {content}"
        self.entry["content"] = (self.entry["content"] + line).strip()


T = typing.TypeVar("T")


def yield_from(gen: typing.Generator[typing.Any, None, T]) -> T:
    """Same as `yield from` but returns the value of the generator."""
    while True:
        try:
            next(gen)
        except StopIteration as e:
            return e.value


def handle_transfer_call_button(
    content: list[dict], openai_ws: ClientConnection, call_sid: str, bi_id: str
):
    """
    Handle a transfer call button if present in the response item.
    Raises ConnectionClosed if a transfer was initiated.
    """

    from daras_ai_v2.bots import parse_bot_html
    from twilio.twiml.voice_response import VoiceResponse
    from routers.bots_api import api_hashids
    from bots.models.bot_integration import validate_phonenumber

    text_content = None
    for part in content:
        if not isinstance(part, dict):
            continue

        if part.get("type") == "text":
            text_content = part.get("text", "")
            break
        elif part.get("type") == "audio":
            text_content = part.get("transcript", "")
            break
    if not text_content:
        return

    buttons, _, _ = parse_bot_html(text_content)

    for button in buttons:
        if "transfer_call" not in button.get("id", ""):
            continue
        transfer_number = button.get("title", "").strip()
        if not transfer_number:
            continue

        # Validate the phone number before attempting transfer
        try:
            validate_phonenumber(transfer_number)
        except ValidationError as e:
            send_json(
                openai_ws,
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Invalid phone number format: {str(e)}",
                            }
                        ],
                    },
                },
            )
            send_json(openai_ws, {"type": "response.create"})
            return

        try:
            bi_id_decoded = api_hashids.decode(bi_id)[0]
            bi = BotIntegration.objects.get(id=bi_id_decoded)
        except BotIntegration.DoesNotExist as e:
            logger.debug(
                f"could not find bot integration with bot_id={bi_id}, call_sid={call_sid} {e}"
            )
            capture_exception(e)
            return

        client = bi.get_twilio_client()

        # try to transfer the call
        resp = VoiceResponse()
        resp.dial(transfer_number)
        try:
            client.calls(call_sid).update(twiml=str(resp))
        except TwilioRestException as e:
            logger.error(f"Failed to transfer call: {e}")
            capture_exception(e)

            send_json(
                openai_ws,
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Failed to transfer call: {str(e)}",
                            }
                        ],
                    },
                },
            )
            send_json(openai_ws, {"type": "response.create"})
        else:
            logger.info(f"Successfully initiated transfer to {transfer_number}")
            raise CallTransferred


class CallTransferred(Exception):
    pass
