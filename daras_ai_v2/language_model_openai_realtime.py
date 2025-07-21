from __future__ import annotations

import json
import threading
import typing
from datetime import datetime

import openai
from furl import furl
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import ClientConnection
from functions.inbuilt_tools import CallTransferLLMTool
from functions.recipe_functions import BaseLLMTool
from .language_model_openai_ws_tools import send_json, recv_json
import logging

# Disable websocket logging
logging.getLogger("websockets").setLevel(logging.WARNING)


if typing.TYPE_CHECKING:
    from daras_ai_v2.language_model import LargeLanguageModels


# adapted from: https://github.com/openai/openai-realtime-twilio-demo/blob/main/websocket-server/src/sessionManager.ts
class RealtimeSession:
    def __init__(
        self,
        twilio_ws: ClientConnection,
        openai_ws: ClientConnection,
        tools: list[BaseLLMTool] | None = None,
        messages: list[dict] | None = None,
        audio_url: str | None = None,
        model: LargeLanguageModels | None = None,
    ):
        self.twilio_ws = twilio_ws
        self.openai_ws = openai_ws
        self.model = model
        self.tools_by_name = {tool.name: tool for tool in tools}
        self.messages = messages or []

        self.audio_url = audio_url
        self.bi_id = furl(audio_url).args.get("bi_id")

        self.stream_sid: str | None = None
        self.call_sid: str | None = None
        self.last_assistant_item_id: str | None = None
        self.response_start_ts: int | None = None
        self.latest_media_ts: int = 0
        self.last_mark: str | None = None
        self.awaiting_threads: list[threading.Thread] = []
        self.is_bridged: bool = False

        self.session_totals = {"input_tokens": 0, "output_tokens": 0}
        # transcript
        self.entry = {"role": "assistant", "content": "", "chunk": ""}

    def stream(self):
        while not (self.stream_sid and self.call_sid):
            msg = recv_json(self.twilio_ws)
            self.stream_sid = msg.get("streamSid")
            start_data = msg.get("start") or {}
            self.call_sid = start_data.get("callSid")

        # Bind context to existing CallTransferLLMTool
        if self.bi_id and self.call_sid and self.tools_by_name:
            for tool in self.tools_by_name.values():
                if isinstance(tool, CallTransferLLMTool):
                    tool.bind(call_sid=self.call_sid, bi_id=self.bi_id)
                    break

        threading.Thread(target=self.pipe_twilio_audio_to_openai).start()

        dispatch = {
            "input_audio_buffer.speech_started": self.on_speech_started,
            "response.audio.delta": self.on_audio_delta,
            "conversation.item.input_audio_transcription.completed": self.on_transcription_completed,
            "response.output_item.done": self.on_output_item_done,
            "response.done": self.on_response_done,
        }
        try:
            while True:
                try:
                    event = recv_json(self.openai_ws)
                except openai.OpenAIError:
                    continue
                handler = dispatch.get(event.get("type"))
                if not handler:
                    continue
                handler(event)
        except ConnectionClosed:
            self.record_session_and_call_costs()
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
        self.last_assistant_item_id = event["item_id"]
        event_id = event["event_id"]
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
            {
                "event": "mark",
                "streamSid": self.stream_sid,
                "mark": {"name": event_id},
            },
        )
        self.last_mark = event_id

    def on_transcription_completed(self, event: dict):
        transcript = event.get("transcript")
        if not transcript:
            return
        self.append_transcription_entry("user", transcript)

    def on_output_item_done(self, event: dict):
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
        if self.tools_by_name and item.get("type") == "function_call":
            self.handle_function_call(item)

    def on_response_done(self, event: dict):
        usage = event["response"]["usage"]
        if usage:
            self.session_totals["input_tokens"] += usage["input_tokens"]
            self.session_totals["output_tokens"] += usage["output_tokens"]

    def handle_function_call(self, function_call: dict):
        from recipes.VideoBots import get_tool_from_call

        call_id = function_call["call_id"]
        self.messages.append(
            dict(
                role="assistant",
                content="",
                tool_calls=[
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": function_call["name"],
                            "arguments": function_call["arguments"],
                        },
                    }
                ],
            )
        )

        tool, arguments = get_tool_from_call(function_call, self.tools_by_name)
        thread = threading.Thread(
            target=self.call_tool, args=(call_id, tool, arguments)
        )
        if self.last_mark and tool.await_audio_completed:
            self.awaiting_threads.append(thread)
        else:
            thread.start()

    def call_tool(self, call_id: str, tool: BaseLLMTool, arguments: str):
        output = tool.call_json(arguments)

        if isinstance(tool, CallTransferLLMTool):
            output = json.loads(output)
            if output.get("success"):
                self.is_bridged = True

        self.messages.append(dict(role="tool", content=output, tool_call_id=call_id))

        send_json(
            self.openai_ws,
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": output,
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
                    case "mark":
                        if msg.get("mark", {}).get("name") == self.last_mark:
                            self.last_mark = None
                            for thread in self.awaiting_threads:
                                thread.start()
                            self.awaiting_threads = []
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
        self.messages.append(dict(role=role, content=content))

    def record_session_and_call_costs(self):
        from usage_costs.cost_utils import record_cost_auto
        from usage_costs.models import ModelSku
        from daras_ai_v2.twilio_bot import IVRPlatformMedium
        from daras_ai_v2.twilio_bot import get_twilio_voice_duration
        from daras_ai_v2.twilio_bot import get_twilio_voice_pricing
        from daras_ai_v2.twilio_bot import get_child_call_sids

        # record llm usage costs
        if self.session_totals["input_tokens"] > 0:
            record_cost_auto(
                model=self.model.model_id,
                sku=ModelSku.llm_prompt,
                quantity=self.session_totals["input_tokens"],
            )

        if self.session_totals["output_tokens"] > 0:
            record_cost_auto(
                model=self.model.model_id,
                sku=ModelSku.llm_completion,
                quantity=self.session_totals["output_tokens"],
            )

        # record IVR usage costs
        call_sids = [self.call_sid]
        if self.is_bridged:
            call_sids += get_child_call_sids(self.bi_id, self.call_sid)

        for call_sid in call_sids:
            duration_seconds = get_twilio_voice_duration(call_sid)
            pricing_per_minute = get_twilio_voice_pricing(self.bi_id, call_sid)

            if duration_seconds > 0:
                record_cost_auto(
                    model=IVRPlatformMedium.twilio_voice.value,
                    sku=ModelSku.ivr_call,
                    quantity=duration_seconds,
                    ivr_price_per_minute=pricing_per_minute,
                )


T = typing.TypeVar("T")


def yield_from(gen: typing.Generator[typing.Any, None, T]) -> T:
    """Same as `yield from` but returns the value of the generator."""
    while True:
        try:
            next(gen)
        except StopIteration as e:
            return e.value
