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

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import settings
from daras_ai_v2.asr import audio_bytes_to_wav
from daras_ai_v2.exceptions import raise_for_status, ffmpeg
from functions.recipe_functions import LLMTool

if typing.TYPE_CHECKING:
    from daras_ai_v2.language_model import LargeLanguageModels

threadlocal = threading.local()


def run_openai_audio(
    *,
    model: LargeLanguageModels,
    audio_url: str,
    messages: list,
    temperature: float | None = None,
    tools: list[LLMTool] | None = None,
    start_chunk_size: int = 50,
    stop_chunk_size: int = 400,
    step_chunk_size: int = 300,
):
    ws, created = get_or_create_ws(model)

    # only send audio if we are creating a new session
    if audio_url and created:
        response = requests.get(audio_url)
        raise_for_status(response, is_user_url=True)
        wav_bytes = audio_bytes_to_wav(response.content)[0] or response.content
        audio_data = base64.b64encode(wav_bytes).decode()
    else:
        audio_data = None

    has_tool_calls = False
    try:
        init_ws_session(
            ws=ws,
            created=created,
            audio_data=audio_data,
            messages=messages,
            temperature=temperature,
            tools=tools,
        )
        send_json(ws, {"type": "response.create"})
        for entry in stream_ws_resposne(
            ws=ws,
            model=model,
            wait_for_transcript=bool(audio_data),
            start_chunk_size=start_chunk_size,
            stop_chunk_size=stop_chunk_size,
            step_chunk_size=step_chunk_size,
        ):
            if entry.get("tool_calls"):
                has_tool_calls = True
            yield [entry]
    finally:
        if has_tool_calls:
            threadlocal._realtime_ws = ws
        else:
            ws.close()
            try:
                del threadlocal._realtime_ws
            except AttributeError:
                pass


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
        "voice": "ash",
        "input_audio_transcription": {"model": "whisper-1"},
        "turn_detection": None,
        "temperature": temperature,
        # "max_response_output_tokens": "inf",
    }
    if tools:
        session_data["tools"] = [
            tool.spec["function"] | {"type": tool.spec["type"]} for tool in tools
        ]
    send_recv_json(ws, {"type": "session.update", "session": session_data})

    if audio_data:
        send_json(ws, {"type": "input_audio_buffer.append", "audio": audio_data})
        send_recv_json(ws, {"type": "input_audio_buffer.commit"})


def stream_ws_resposne(
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

    ouput_pcm = b""
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
                ouput_pcm += base64.b64decode(event["delta"])

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

    if ouput_pcm:
        with (
            tempfile.NamedTemporaryFile(suffix=".pcm") as infile,
            tempfile.NamedTemporaryFile(suffix=".mp3") as outfile,
        ):
            infile.write(ouput_pcm)
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
