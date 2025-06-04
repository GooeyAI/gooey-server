from __future__ import annotations

import base64
import json
import tempfile
import threading
import typing
from datetime import datetime

import openai
import requests
from furl import furl
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect, ClientConnection

from sentry_sdk import capture_exception
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import settings
from daras_ai_v2.asr import audio_bytes_to_wav
from daras_ai_v2.exceptions import raise_for_status, ffmpeg
from django.core.exceptions import ValidationError
from bots.models import BotIntegration
from functions.recipe_functions import LLMTool
from twilio.base.exceptions import TwilioRestException
from loguru import logger

if typing.TYPE_CHECKING:
    from daras_ai_v2.language_model import LargeLanguageModels

threadlocal = threading.local()


def run_openai_audio(
    *,
    model: LargeLanguageModels,
    audio_url: str | None,
    audio_session_extra: dict | None,
    messages: list,
    temperature: float | None = None,
    tools: list[LLMTool] | None = None,
    start_chunk_size: int = 50,
    stop_chunk_size: int = 400,
    step_chunk_size: int = 300,
):
    openai_ws, created = get_or_create_ws(model)

    twilio_ws = None
    audio_data = None
    if audio_url and audio_url.startswith("ws"):
        # if the audio_url is a websocket url, connect to it
        twilio_ws = connect(audio_url)
        audio_session_extra = (audio_session_extra or {}) | {
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "turn_detection": {"type": "server_vad"},
        }
    elif audio_url and created:
        # only send audio if we are creating a new session
        response = requests.get(audio_url)
        raise_for_status(response, is_user_url=True)
        wav_bytes = audio_bytes_to_wav(response.content)[0] or response.content
        audio_data = base64.b64encode(wav_bytes).decode()

    has_tool_calls = False
    try:
        init_ws_session(
            ws=openai_ws,
            created=created,
            audio_data=audio_data,
            audio_session_extra=audio_session_extra,
            messages=messages,
            temperature=temperature,
            tools=tools,
        )
        if twilio_ws:
            for entry in RealtimeSession(
                twilio_ws, openai_ws, tools, audio_url
            ).stream():
                yield [entry]
        else:
            send_json(openai_ws, {"type": "response.create"})
            for entry in stream_ws_response(
                ws=openai_ws,
                model=model,
                wait_for_transcript=bool(audio_data),
                start_chunk_size=start_chunk_size,
                stop_chunk_size=stop_chunk_size,
                step_chunk_size=step_chunk_size,
            ):
                if entry.get("tool_calls"):
                    has_tool_calls = True
                yield [entry]
    except ConnectionClosed:
        pass
    finally:
        if has_tool_calls:
            threadlocal._realtime_ws = openai_ws
        else:
            openai_ws.close()
            try:
                del threadlocal._realtime_ws
            except AttributeError:
                pass
        if twilio_ws:
            twilio_ws.close()


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

        # pipe audio from Twilio to OpenAI
        threading.Thread(target=self.pipe_audio).start()

        dispatch = {
            "input_audio_buffer.speech_started": self.on_speech_started,
            "conversation.item.input_audio_transcription.completed": self.on_transcription_completed,
            "response.audio.delta": self.on_audio_delta,
            "response.output_item.done": self.on_output_item_done,
        }
        try:
            while True:
                event = recv_json(self.openai_ws)
                handler = dispatch.get(event.get("type"))
                if not handler:
                    continue
                handler(event)
        except ConnectionClosed:
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

    def on_transcription_completed(self, event: dict):
        if not event.get("transcript"):
            return
        self.entry["content"] += format_transcription_entry(
            "user",
            event["transcript"],
            self.response_start_ts,
        )

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
                self.entry["content"] += format_transcription_entry(
                    "assistant",
                    transcript,
                    self.response_start_ts,
                )
            if self.bi_id and handle_transfer_call_button(
                content, self.openai_ws, self.call_sid, self.bi_id
            ):
                raise ConnectionClosed

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

    def pipe_audio(self):
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


def format_transcription_entry(role: str, content: str, conversation_start: datetime):
    elapsed = datetime.now() - conversation_start
    return (
        f"[{elapsed.minute:02d}:{elapsed.second:02d}] {role.title()}: {content.strip()}"
    )


T = typing.TypeVar("T")


def yield_from(gen: typing.Generator[typing.Any, None, T]) -> T:
    """Same as `yield from` but returns the value of the generator."""
    while True:
        try:
            next(gen)
        except StopIteration as e:
            return e.value


def get_or_create_ws(model) -> tuple[ClientConnection, bool]:
    try:
        ws = threadlocal._realtime_ws
        created = False
    except AttributeError:
        ws = connect(
            furl(
                "wss://api.openai.com/v1/realtime",
                query_params={"model": model.model_id},
            ).url,
            additional_headers={
                "Authorization": "Bearer " + settings.OPENAI_API_KEY,
                "OpenAI-Beta": "realtime=v1",
            },
        )
        created = True
    return ws, created


def init_ws_session(
    ws: ClientConnection,
    created: bool,
    audio_data: str | None,
    audio_session_extra: dict | None,
    messages: list,
    temperature: float | None = None,
    tools: list[LLMTool] | None = None,
):
    from daras_ai_v2.language_model import get_entry_text, msgs_to_prompt_str

    if not created:
        # session already exists, just send back the most recent tool outputs
        for entry in reversed(messages):
            if entry.get("role") != "tool":
                break
            send_recv_json(
                ws,
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": entry.get("tool_call_id"),
                        "output": entry.get("content"),
                    },
                },
            )
        return

    # wait for the initial response
    recv_json(ws)

    system_message = "\n\n".join(
        get_entry_text(entry) for entry in messages if entry.get("role") == "system"
    )
    conversation = [
        entry for entry in messages if entry.get("role") in {"user", "assistant"}
    ]
    if conversation:
        system_message += (
            "Previous Conversation Transcript:\n----------\n"
            + msgs_to_prompt_str(conversation)
        )

    session_data = {
        "instructions": system_message,
        "input_audio_transcription": {"model": "whisper-1"},
        "turn_detection": None,
        "temperature": temperature,
        # "max_response_output_tokens": "inf",
    }
    if audio_session_extra:
        session_data |= audio_session_extra
    if tools:
        session_data["tools"] = [
            tool.spec["function"] | {"type": tool.spec["type"]} for tool in tools
        ]
    send_recv_json(ws, {"type": "session.update", "session": session_data})

    if audio_data:
        send_json(ws, {"type": "input_audio_buffer.append", "audio": audio_data})
        send_recv_json(ws, {"type": "input_audio_buffer.commit"})


def stream_ws_response(
    ws: ClientConnection,
    model: LargeLanguageModels,
    wait_for_transcript: bool,
    start_chunk_size: int = 50,
    stop_chunk_size: int = 400,
    step_chunk_size: int = 300,
):
    from daras_ai_v2.language_model import is_llm_chunk_large_enough
    from usage_costs.models import ModelSku
    from usage_costs.cost_utils import record_cost_auto

    output_pcm = b""
    input_audio_transcript = None
    output = None
    entry = {"role": "assistant", "content": "", "chunk": ""}
    chunk_size = start_chunk_size

    while output is None or (wait_for_transcript and input_audio_transcript is None):
        event = recv_json(ws)
        match event.get("type"):
            case "response.audio_transcript.delta" | "response.text.delta":
                entry["chunk"] += event["delta"]
                if is_llm_chunk_large_enough(entry, chunk_size):
                    # increase the chunk size, but don't go over the max
                    chunk_size = min(chunk_size + step_chunk_size, stop_chunk_size)
                    # stream the chunk
                    yield entry

            case "response.audio.delta":
                output_pcm += base64.b64decode(event["delta"])

            case "conversation.item.input_audio_transcription.completed":
                input_audio_transcript = event["transcript"]

            case "response.done":
                output = event["response"]["output"]
                entry["tool_calls"] = [
                    {
                        "id": entry["call_id"],
                        "function": {
                            "name": entry["name"],
                            "arguments": entry["arguments"],
                        },
                    }
                    for entry in output
                    if entry.get("type") == "function_call"
                ]
                usage = event["response"]["usage"]
                if usage:
                    record_cost_auto(
                        model=model.model_id,
                        sku=ModelSku.llm_prompt,
                        quantity=usage["input_tokens"],
                    )
                    record_cost_auto(
                        model=model.model_id,
                        sku=ModelSku.llm_completion,
                        quantity=usage["output_tokens"],
                    )

    # add the leftover chunks
    entry["content"] += entry["chunk"]
    if input_audio_transcript is not None:
        entry["input_audio_transcript"] = input_audio_transcript

    if output_pcm:
        with (
            tempfile.NamedTemporaryFile(suffix=".pcm") as infile,
            tempfile.NamedTemporaryFile(suffix=".mp3") as outfile,
        ):
            infile.write(output_pcm)
            infile.flush()
            ffmpeg(
                "-f", "s16le", "-ar", "24k", "-ac", "1", "-i", infile.name, outfile.name
            )
            audio_data = outfile.read()
        entry["audio_url"] = upload_file_from_bytes(
            "copilot_audio_out.mp3", audio_data, "audio/mpeg"
        )

    yield entry


def send_recv_json(ws: ClientConnection, event: dict) -> dict:
    drain(ws)
    send_json(ws, event)
    return recv_json(ws)


def send_json(ws: ClientConnection, event: dict):
    try:
        ws.send(json.dumps(event))
        # print(f"> {event=}")
    except ConnectionClosed:
        drain(ws)
        raise


def drain(ws: ClientConnection):
    while True:
        try:
            recv_json(ws, timeout=0)
        except TimeoutError:
            return


def recv_json(ws: ClientConnection, **kwargs) -> dict:
    event = json.loads(ws.recv(**kwargs))
    # print(f"< {event=}")
    if event.get("type") in {
        "error",
        "response.failed",
        "response.incomplete",
    } or event.get("response", {}).get("status") in {
        "failed",
        "incomplete",
    }:
        raise openai.OpenAIError(event)
    return event


def handle_transfer_call_button(
    content: list[dict], openai_ws: ClientConnection, call_sid: str, bi_id: str
) -> bool:
    """Handle a transfer call button if present in the response item.
    Returns True if a transfer was initiated, False otherwise."""
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
        return False

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
            return False

        try:
            bi_id_decoded = api_hashids.decode(bi_id)[0]
            bi = BotIntegration.objects.get(id=bi_id_decoded)

        except BotIntegration.DoesNotExist as e:
            logger.debug(
                f"could not find bot integration with bot_id={bi_id}, call_sid={call_sid} {e}"
            )
            capture_exception(e)
            return False

        client = bi.get_twilio_client()

        # try to transfer the call
        try:
            resp = VoiceResponse()
            resp.dial(transfer_number)
            client.calls(call_sid).update(twiml=str(resp))
            logger.info(f"Successfully initiated transfer to {transfer_number}")

            return True
        except TwilioRestException as e:
            logger.error(f"Failed to transfer call: {e}")

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
            capture_exception(e)
            return False

    return False
