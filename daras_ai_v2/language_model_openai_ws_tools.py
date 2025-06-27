from __future__ import annotations

import json

import openai
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import ClientConnection


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
    # if event.get("event") == "media":
    #     pass
    # elif event.get("type") == "response.audio.delta":
    #     print(f"< event={event | {'delta': len(event['delta'])}}")
    # else:
    #     print(f"< {event=}")
    if event.get("type") in {
        "error",
        "response.failed",
        "response.incomplete",
    } or event.get("response", {}).get("status") in {
        "failed",
        # "incomplete",
    }:
        raise openai.OpenAIError(event)
    return event
