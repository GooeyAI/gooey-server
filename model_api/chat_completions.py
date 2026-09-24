import asyncio
import json
import typing

import anyio
import litellm
import sentry_sdk
from fastapi import APIRouter, Depends, HTTPException
from litellm.types.utils import ModelResponseStream
from openai.types.chat.completion_create_params import CompletionCreateParamsBase
from pydantic import BaseModel, ConfigDict
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from ai_models.models import AIModelSpec, ModelProvider
from api_keys.models import ApiKey
from auth.token_authentication import api_auth_header

router = APIRouter()

# Only OpenAI Chat Completions params reach LiteLLM. Everything else (OpenRouter
# extras, and LiteLLM kwargs like api_base / api_key) is dropped, so a caller can't
# redirect the model row's credentials.
# TODO: a strict per-field whitelist that validates values; drop_params=True for now
FORWARDED_PARAMS = frozenset(CompletionCreateParamsBase.__annotations__) - {
    "model",
    "messages",
    "stream",
    "stream_options",
}

ERROR_TYPES = {
    400: "invalid_request_error",
    401: "authentication_error",
    402: "insufficient_credits",
    403: "permission_error",
    404: "not_found_error",
    429: "rate_limit_error",
}

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[dict]
    stream: bool = False


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
    api_key: ApiKey = Depends(api_auth_header),
):
    # TODO: check credits (ensure_credits_and_auto_recharge) and price the usage
    # TODO: persist a Saved Run, and stop the upstream call when it's cancelled
    # TODO: vision, audio and file content parts
    spec = await get_model_spec(body.model)
    kwargs = build_completion_kwargs(spec, body)

    if not body.stream:
        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as e:
            return upstream_error_response(e)
        response.model = spec.name
        return JSONResponse(response.model_dump(exclude_none=True))

    try:
        started = await start_stream_unless_disconnected(request, kwargs)
    except Exception as e:
        return upstream_error_response(e)
    if not started:
        # client went away before the first chunk; nobody is listening
        return Response(status_code=499)
    stream, first_chunk = started
    # TODO: send `: keepalive` comments during long gaps between chunks
    return UpstreamClosingStreamingResponse(
        stream_sse_events(spec, stream, first_chunk),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


async def get_model_spec(name: str) -> AIModelSpec:
    try:
        return await AIModelSpec.objects.aget(
            name=name, provider=ModelProvider.litellm_responses
        )
    except AIModelSpec.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"Model {name!r} not found.")


def build_completion_kwargs(spec: AIModelSpec, body: ChatCompletionRequest) -> dict:
    kwargs = {
        key: value
        for key, value in (body.model_extra or {}).items()
        if key in FORWARDED_PARAMS
    }
    kwargs.update(
        model=spec.model_id,
        messages=body.messages,
        stream=body.stream,
        drop_params=True,
    )
    if body.stream:
        kwargs["stream_options"] = {"include_usage": True}
    if spec.api_key:
        kwargs["api_key"] = spec.api_key
    if spec.base_url:
        kwargs["api_base"] = spec.base_url
    if spec.model_id.startswith(("vertex_ai/", "vertex_ai_beta/")):
        kwargs["vertex_location"] = "global"
    return kwargs


async def start_stream_unless_disconnected(
    request: Request, kwargs: dict
) -> tuple[litellm.CustomStreamWrapper, ModelResponseStream] | None:
    """
    Open the upstream stream and read its first chunk before any response headers
    go out, so upstream errors still get a proper HTTP status. Returns None if the
    client disconnects first, after cancelling (and so closing) the upstream call.
    """
    start = asyncio.ensure_future(start_stream(kwargs))
    disconnect = asyncio.ensure_future(wait_for_disconnect(request))
    try:
        await asyncio.wait({start, disconnect}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        disconnect.cancel()
    if start.done():
        return start.result()
    start.cancel()
    try:
        await start
    except asyncio.CancelledError:
        pass
    return None


async def start_stream(
    kwargs: dict,
) -> tuple[litellm.CustomStreamWrapper, ModelResponseStream]:
    stream = await litellm.acompletion(**kwargs)
    try:
        return stream, await stream.__anext__()
    except BaseException:
        await stream.aclose()
        raise


async def wait_for_disconnect(request: Request):
    while (await request.receive())["type"] != "http.disconnect":
        pass


async def stream_sse_events(
    spec: AIModelSpec,
    stream: litellm.CustomStreamWrapper,
    first_chunk: ModelResponseStream,
) -> typing.AsyncIterator[str]:
    try:
        yield format_sse_chunk(spec, first_chunk)
        async for chunk in stream:
            yield format_sse_chunk(spec, chunk)
    except Exception as e:
        yield "data: " + json.dumps(stream_error_chunk(e)) + "\n\n"
    finally:
        # CustomStreamWrapper.aclose() shields itself from cancellation
        await stream.aclose()
    yield "data: [DONE]\n\n"


def format_sse_chunk(spec: AIModelSpec, chunk: ModelResponseStream) -> str:
    # LiteLLM's final usage chunk keeps one empty choice (OpenAI sends none). OpenCode
    # accepts both, and clients that index choices[0] don't break on this one.
    chunk.model = spec.name
    return (
        "data: " + chunk.model_dump_json(exclude_none=True, exclude_unset=True) + "\n\n"
    )


def stream_error_chunk(exc: Exception) -> dict:
    status_code = upstream_status_code(exc)
    return error_body(status_code, str(exc)) | {
        "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}]
    }


def upstream_error_response(exc: Exception) -> JSONResponse:
    return error_response(upstream_status_code(exc), str(exc))


def upstream_status_code(exc: Exception) -> int:
    status_code = getattr(exc, "status_code", None) or 500
    if status_code in (401, 403):
        # the model row's provider credentials failed, not the caller's Gooey key
        status_code = 502
    if status_code >= 500:
        sentry_sdk.capture_exception(exc)
    return status_code


def error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(error_body(status_code, message), status_code=status_code)


def error_body(status_code: int, message: str) -> dict:
    return {
        "error": {
            "code": status_code,
            "message": message,
            "type": ERROR_TYPES.get(status_code, "api_error"),
        }
    }


class UpstreamClosingStreamingResponse(StreamingResponse):
    """
    Starlette abandons the body iterator when the client disconnects mid-stream,
    which would leave the upstream LLM stream open until garbage collection.
    Close it explicitly so the generator's `finally` runs `stream.aclose()`.
    """

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()
