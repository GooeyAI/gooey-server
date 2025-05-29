from __future__ import annotations

import base64
import json
import tempfile
import threading
import typing

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
            handle_twilio_ws(twilio_ws, openai_ws, tools, audio_url)
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
def handle_twilio_ws(
    twilio_ws: ClientConnection,
    openai_ws: ClientConnection,
    tools: list[LLMTool] | None = None,
    audio_url: str | None = None,
):
    stream_sid = None
    call_sid = None
    bi_id = furl(audio_url).args.get("bi_id") or None
    while not (stream_sid and call_sid):
        msg = recv_json(twilio_ws)
        stream_sid = msg.get("streamSid")
        start_data = msg.get("start") or {}
        call_sid = start_data.get("callSid")

    last_assistant_item_id = None
    response_start_ts = None
    latest_media_ts = {"val": 0}

    # pipe audio from Twilio to OpenAI
    threading.Thread(
        target=pipe_audio, args=(twilio_ws, openai_ws, latest_media_ts)
    ).start()

    while True:
        event = recv_json(openai_ws)
        match event.get("type"):
            case "input_audio_buffer.speech_started":
                if not (last_assistant_item_id and response_start_ts):
                    continue
                # send_json(
                #     openai_ws,
                #     {
                #         "type": "conversation.item.truncate",
                #         "item_id": last_assistant_item_id,
                #         "content_index": 0,
                #         "audio_end_ms": max(
                #             latest_media_ts["val"] - response_start_ts, 0
                #         ),
                #     },
                # )
                send_json(
                    twilio_ws,
                    {"event": "clear", "streamSid": stream_sid},
                )
                last_assistant_item_id = None
                response_start_ts = None

            case "response.audio.delta":
                if response_start_ts is None:
                    response_start_ts = latest_media_ts["val"]
                item_id = event.get("item_id")
                if item_id:
                    last_assistant_item_id = item_id
                send_json(
                    twilio_ws,
                    {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload": event["delta"]},
                    },
                )
                send_json(
                    twilio_ws,
                    {"event": "mark", "streamSid": stream_sid},
                )

            case "response.output_item.done":
                from recipes.VideoBots import exec_tool_call

                if not tools:
                    continue
                item = event.get("item")

                if not item:
                    continue

                if handle_transfer_call_button(openai_ws, item, call_sid, bi_id):
                    break

                # Handle function calls
                if item.get("type") != "function_call":
                    continue
                result = yield_from(
                    exec_tool_call(
                        {"function": item},
                        {tool.name: tool for tool in tools},
                    )
                )
                send_json(
                    openai_ws,
                    {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "function_call_output",
                            "call_id": item["call_id"],
                            "output": json.dumps(result),
                        },
                    },
                )
                send_json(openai_ws, {"type": "response.create"})


T = typing.TypeVar("T")


def yield_from(gen: typing.Generator[typing.Any, None, T]) -> T:
    """Same as `yield from` but returns the value of the generator."""
    while True:
        try:
            next(gen)
        except StopIteration as e:
            return e.value


def pipe_audio(
    twilio_ws: ClientConnection, openai_ws: ClientConnection, latest_media_ts: dict
):
    try:
        while True:
            msg = recv_json(twilio_ws)
            match msg.get("event"):
                case "stop":
                    break
                case "media":
                    media = msg.get("media")
                    if not media:
                        continue
                    latest_media_ts["val"] = int(media["timestamp"])
                    send_json(
                        openai_ws,
                        {
                            "type": "input_audio_buffer.append",
                            "audio": media["payload"],
                        },
                    )
    except ConnectionClosed:
        pass
    finally:
        openai_ws.close()


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
    openai_ws: ClientConnection, item: dict, call_sid: str, bi_id: str | None
) -> bool:
    """Handle a transfer call button if present in the response item.
    Returns True if a transfer was initiated, False otherwise."""
    from daras_ai_v2.bots import parse_bot_html
    from twilio.twiml.voice_response import VoiceResponse
    from routers.bots_api import api_hashids
    from bots.models.bot_integration import validate_phonenumber

    content = item.get("content") or []
    if not content or not bi_id:
        return False

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
