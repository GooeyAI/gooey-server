import asyncio
import json
import math
import typing
import uuid

import anyio
import litellm
import sentry_sdk
from asgiref.sync import sync_to_async
from fastapi import APIRouter, Depends, HTTPException
from litellm.types.utils import ModelResponseStream, Usage
from openai.types.chat.completion_create_params import CompletionCreateParamsBase
from pydantic import BaseModel, ConfigDict
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from ai_models.models import AIModelSpec, ModelProvider
from api_keys.models import ApiKey
from auth.token_authentication import api_auth_header
from bots.models import Workflow
from daras_ai_v2 import settings
from gooeysite.bg_db_conn import db_middleware
from payments.plans import PricingPlan
from recipes.CompareLLM import CompareLLMPage
from usage_costs.cost_utils import get_model_pricing
from usage_costs.models import ModelSku
from workspaces.models import Workspace, WorkspaceMembership

router = APIRouter()


# CONN_MAX_AGE=None keeps connections open forever; db_middleware recycles stale ones
@db_middleware
def api_auth(request: Request) -> ApiKey:
    return api_auth_header(request)


# Only OpenAI Chat Completions params reach LiteLLM. Everything else (OpenRouter
# extras, and LiteLLM kwargs like api_base / api_key) is dropped, so a caller can't
# redirect the model row's credentials. Params whose cost isn't billed as prompt or
# completion tokens (extra outputs, priority tiers, audio, web search) are dropped
# too, since the charge only covers tokens.
# TODO: a strict per-field whitelist that validates values; drop_params=True for now
FORWARDED_PARAMS = frozenset(CompletionCreateParamsBase.__annotations__) - {
    "model",
    "messages",
    "stream",
    "stream_options",
    "n",
    "service_tier",
    "web_search_options",
    "audio",
    "modalities",
    "store",
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
    api_key: ApiKey = Depends(api_auth),
):
    # TODO: persist a Saved Run, and stop the upstream call when it's cancelled
    # TODO: vision, audio and file content parts
    spec = await sync_to_async(get_model_spec)(body.model)
    kwargs = build_completion_kwargs(spec, body)
    payer = await sync_to_async(get_payer_with_credits)(api_key, spec, kwargs)

    if not body.stream:
        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as e:
            return upstream_error_response(e)
        await charge(payer, api_key, spec, response.usage)
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
        stream_sse_events(spec, payer, api_key, body.messages, stream, first_chunk),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@db_middleware
def get_model_spec(name: str) -> AIModelSpec:
    """
    Serve only allowlisted, non-deprecated LiteLLM rows that have token pricing and
    an output limit, so every call can be charged and its worst case is known.
    """
    spec = None
    if name in settings.MODEL_API_ALLOWED_MODELS:
        spec = AIModelSpec.objects.filter(
            name=name,
            provider=ModelProvider.litellm_responses,
            category=AIModelSpec.Categories.llm,
            is_deprecated=False,
            llm_max_output_tokens__gt=0,
        ).first()
    if not spec or not all(
        get_model_pricing(spec.model_id, sku)
        for sku in (ModelSku.llm_prompt, ModelSku.llm_completion)
    ):
        raise HTTPException(status_code=404, detail=f"Model {name!r} not found.")
    return spec


@db_middleware
def get_payer_with_credits(
    api_key: ApiKey, spec: AIModelSpec, kwargs: dict
) -> Workspace | WorkspaceMembership:
    """
    Mirrors BasePage.ensure_credits_and_auto_recharge: TEAM plans pay from the
    member's balance, everyone else from the workspace's. The balance must cover
    the most this call can cost, so one call can't overdraw it.
    """
    # TODO: auto-recharge like ensure_credits_and_auto_recharge
    workspace = api_key.workspace
    payer = workspace
    if PricingPlan.from_sub(workspace.subscription) == PricingPlan.TEAM:
        payer = workspace.memberships.filter(
            user=api_key.created_by, deleted__isnull=True
        ).first()
        if not payer:
            raise HTTPException(
                status_code=403,
                detail="The creator of this API key is no longer part of the workspace.",
            )
    max_price = price_in_credits(spec, max_usage(spec, kwargs))
    if payer.balance < max_price:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient credits: this request can cost up to {max_price} "
            f"credits and the balance is {payer.balance}. Lower max_tokens, or add "
            "credits at https://gooey.ai/account/billing/",
        )
    return payer


def max_usage(spec: AIModelSpec, kwargs: dict) -> Usage:
    """The most a call can use: its counted prompt plus its capped output."""
    try:
        prompt_tokens = litellm.token_counter(
            model=spec.model_id, messages=kwargs["messages"], tools=kwargs.get("tools")
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid messages: {e}")
    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=kwargs["max_tokens"],
        total_tokens=prompt_tokens + kwargs["max_tokens"],
    )


def build_completion_kwargs(spec: AIModelSpec, body: ChatCompletionRequest) -> dict:
    kwargs = {
        key: value
        for key, value in (body.model_extra or {}).items()
        if key in FORWARDED_PARAMS
    }
    if "tools" in kwargs:
        # provider-hosted tools (web search, grounding) are billed beyond tokens
        kwargs["tools"] = [
            tool
            for tool in kwargs["tools"] or []
            if isinstance(tool, dict) and tool.get("type") == "function"
        ] or None
    # cap the output at the row's limit, so the worst-case charge is known up front;
    # LiteLLM maps max_tokens onto each provider's own field
    requested = [
        kwargs.pop(key, None) for key in ("max_completion_tokens", "max_tokens")
    ]
    kwargs["max_tokens"] = min(
        [n for n in requested if isinstance(n, int) and n > 0]
        + [spec.llm_max_output_tokens]
    )
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
    payer: Workspace | WorkspaceMembership,
    api_key: ApiKey,
    messages: list[dict],
    stream: litellm.CustomStreamWrapper,
    first_chunk: ModelResponseStream,
) -> typing.AsyncIterator[str]:
    chunks = [first_chunk]
    try:
        yield format_sse_chunk(spec, first_chunk)
        async for chunk in stream:
            chunks.append(chunk)
            yield format_sse_chunk(spec, chunk)
    except Exception as e:
        yield "data: " + json.dumps(stream_error_chunk(e)) + "\n\n"
    finally:
        # CustomStreamWrapper.aclose() shields itself from cancellation
        await stream.aclose()
        # charge even when the client disconnects, so leaving early isn't free
        with anyio.CancelScope(shield=True):
            await charge(payer, api_key, spec, stream_usage(chunks, messages))
    yield "data: [DONE]\n\n"


def format_sse_chunk(spec: AIModelSpec, chunk: ModelResponseStream) -> str:
    # LiteLLM's final usage chunk keeps one empty choice (OpenAI sends none). OpenCode
    # accepts both, and clients that index choices[0] don't break on this one.
    chunk = chunk.model_copy(update={"model": spec.name})
    return (
        "data: " + chunk.model_dump_json(exclude_none=True, exclude_unset=True) + "\n\n"
    )


def stream_usage(
    chunks: list[ModelResponseStream], messages: list[dict]
) -> Usage | None:
    for chunk in reversed(chunks):
        if getattr(chunk, "usage", None):
            return chunk.usage
    # the stream stopped before LiteLLM's final usage chunk: count what was streamed
    try:
        return litellm.stream_chunk_builder(chunks, messages=messages).usage
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return None


async def charge(
    payer: Workspace | WorkspaceMembership,
    api_key: ApiKey,
    spec: AIModelSpec,
    usage: Usage | None,
):
    # the response has already been generated; report a failed charge rather than
    # break the response
    try:
        await sync_to_async(charge_for_usage)(payer, api_key, spec, usage)
    except Exception as e:
        sentry_sdk.capture_exception(e)


@db_middleware
def charge_for_usage(
    payer: Workspace | WorkspaceMembership,
    api_key: ApiKey,
    spec: AIModelSpec,
    usage: Usage | None,
):
    """Mirrors BasePage.deduct_credits."""
    amount = price_in_credits(spec, usage)
    invoice_id = f"gooey_in_{uuid.uuid1()}"
    if isinstance(payer, WorkspaceMembership):
        payer.add_balance(amount=-amount, invoice_id=invoice_id)
    else:
        payer.add_balance(
            amount=-amount, invoice_id=invoice_id, user=api_key.created_by
        )


def price_in_credits(spec: AIModelSpec | None, usage: Usage | None) -> int:
    """
    The price the CompareLLM workflow charges for the same call: the tokens at
    ModelPricing rates (as record_openai_llm_usage records them) rounded up to
    credits, plus its profit credits, times its price multiplier. With no usage
    this is the minimum charge.
    """
    dollars = 0
    if spec and usage:
        completion_tokens = usage.completion_tokens or (
            usage.completion_tokens_details
            and usage.completion_tokens_details.reasoning_tokens
        )
        for sku, quantity in (
            (ModelSku.llm_prompt, usage.prompt_tokens),
            (ModelSku.llm_completion, completion_tokens),
        ):
            pricing = get_model_pricing(spec.model_id, sku)
            dollars += pricing.unit_cost * (quantity or 0) / pricing.unit_quantity
    credits = (
        math.ceil(dollars * settings.ADDON_CREDITS_PER_DOLLAR)
        + CompareLLMPage.PROFIT_CREDITS
    )
    multiplier = Workflow.COMPARE_LLM.get_or_create_metadata().price_multiplier
    return max(1, math.ceil(credits * multiplier))


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
