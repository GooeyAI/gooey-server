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

        # Handle function calls
        if self.tools and item.get("type") == "function_call":
            # Check if this is a phone transfer request
            if item["name"] == "get_phone_number" and self.bi_id:
                result = self._handle_phone_transfer(
                    item, call_sid=self.call_sid, bi_id=self.bi_id
                )
            else:
                result = yield_from(
                    exec_tool_call(
                        {"function": item},
                        {tool.name: tool for tool in self.tools},
                    )
                )

            self._send_function_result(item["call_id"], result)

    def _handle_phone_transfer(
        self, item: dict, call_sid: str, bi_id: str
    ) -> str | None:
        try:
            arguments = json.loads(item["arguments"])
            phone_number = arguments.get("phone_number") or ""
        except json.JSONDecodeError as e:
            capture_exception(error=dict(error=repr(e)))
            return None

        try:
            error_message = handle_transfer_call(
                transfer_number=phone_number,
                call_sid=call_sid,
                bi_id=bi_id,
            )
            return error_message
        except CallTransferred:
            raise

    def _send_function_result(self, call_id: str, result: typing.Any):
        if not result:
            return
        send_json(
            self.openai_ws,
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
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


def handle_transfer_call(transfer_number: str, call_sid: str, bi_id: str) -> str | None:
    """
    Handle a transfer call for the get_phone_number function.

    Args:
        transfer_number: Phone number to transfer to
        call_sid: Twilio call SID
        bi_id: Bot integration ID

    Returns:
        Error message string if transfer fails, None if successful

    Raises:
        CallTransferred: If transfer is successful
    """
    from twilio.twiml.voice_response import VoiceResponse
    from routers.bots_api import api_hashids
    from bots.models.bot_integration import validate_phonenumber

    # Validate the phone number before attempting transfer
    try:
        validate_phonenumber(transfer_number)
    except ValidationError as e:
        return f"Invalid phone number format: {str(e)} number should be in E.164 format"

    try:
        bi_id_decoded = api_hashids.decode(bi_id)[0]
        bi = BotIntegration.objects.get(id=bi_id_decoded)
    except BotIntegration.DoesNotExist as e:
        logger.debug(
            f"could not find bot integration with bot_id={bi_id}, call_sid={call_sid} {e}"
        )
        capture_exception(e)
        return None

    client = bi.get_twilio_client()

    # try to transfer the call
    resp = VoiceResponse()
    resp.dial(transfer_number)

    try:
        client.calls(call_sid).update(twiml=str(resp))
    except TwilioRestException as e:
        logger.error(f"Failed to transfer call: {e}")
        capture_exception(e)
        return f"Failed to transfer call: {str(e)}"
    else:
        logger.info(f"Successfully initiated transfer to {transfer_number}")
        raise CallTransferred


class CallTransferred(Exception):
    pass
