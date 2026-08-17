"""Reverse proxy (HTTP + WebSocket) from the gateway to a ComfyUI instance."""

import asyncio
import logging

import httpx
import websockets
from fastapi import Request, WebSocket, WebSocketDisconnect
from starlette.background import BackgroundTask
from starlette.responses import Response, StreamingResponse

logger = logging.getLogger("comfy.proxy")

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    # our session cookie must never leave the gateway
    "cookie",
    # recomputed when we rewrite HTML
    "content-length",
    "content-encoding",
}

_client = httpx.AsyncClient(timeout=httpx.Timeout(60, read=600), follow_redirects=False)


def _clean_headers(headers) -> dict:
    return {
        k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP_HEADERS
    }


async def proxy_http(
    request: Request, upstream_base: str, inject_html: str | None = None
) -> Response:
    url = upstream_base + request.url.path
    if request.url.query:
        url += "?" + request.url.query

    upstream_request = _client.build_request(
        method=request.method,
        url=url,
        headers=_clean_headers(request.headers),
        content=request.stream(),
    )
    upstream = await _client.send(upstream_request, stream=True)

    content_type = upstream.headers.get("content-type", "")
    if inject_html and "text/html" in content_type:
        body = await upstream.aread()
        await upstream.aclose()
        html = body.decode("utf-8", errors="replace")
        idx = html.lower().find("</head>")
        if idx == -1:
            html = inject_html + html
        else:
            html = html[:idx] + inject_html + html[idx:]
        return Response(
            content=html,
            status_code=upstream.status_code,
            headers=_clean_headers(upstream.headers),
            media_type=content_type,
        )

    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        headers=_clean_headers(upstream.headers),
        background=BackgroundTask(upstream.aclose),
    )


async def proxy_websocket(ws: WebSocket, upstream_base: str):
    """Bridge the browser's /ws connection to the upstream ComfyUI websocket."""
    upstream_url = upstream_base.replace("http", "ws", 1) + ws.url.path
    if ws.url.query:
        upstream_url += "?" + ws.url.query

    await ws.accept()
    try:
        async with websockets.connect(
            upstream_url, max_size=64 * 1024 * 1024
        ) as upstream:
            client_to_upstream = asyncio.create_task(_pump_client(ws, upstream))
            upstream_to_client = asyncio.create_task(_pump_upstream(ws, upstream))
            done, pending = await asyncio.wait(
                [client_to_upstream, upstream_to_client],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
    except Exception as e:
        logger.debug(f"websocket bridge closed: {e!r}")
    finally:
        try:
            await ws.close()
        except RuntimeError:
            pass


async def _pump_client(ws: WebSocket, upstream):
    while True:
        message = await ws.receive()
        if message["type"] == "websocket.disconnect":
            return
        if message.get("text") is not None:
            await upstream.send(message["text"])
        elif message.get("bytes") is not None:
            await upstream.send(message["bytes"])


async def _pump_upstream(ws: WebSocket, upstream):
    try:
        async for message in upstream:
            if isinstance(message, bytes):
                await ws.send_bytes(message)
            else:
                await ws.send_text(message)
    except WebSocketDisconnect:
        pass
