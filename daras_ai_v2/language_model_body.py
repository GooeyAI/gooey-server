import typing

import pydantic

from ai_models.models import AIModelSpec

CHATML_ROLE_USER = "user"


class LLMFunction(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="ignore")

    name: str = ""
    arguments: str = ""

    @pydantic.field_validator("name", "arguments", mode="before")
    @classmethod
    def _none_to_empty(cls, v):
        return v or ""


class LLMToolCall(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="ignore")

    id: str = ""
    type: typing.Literal["function"] = "function"
    function: LLMFunction = LLMFunction()

    # used by gemini models
    extra_content: dict[str, typing.Any] | None = None

    @pydantic.field_validator("id", mode="before")
    @classmethod
    def _id_none_to_empty(cls, v):
        return v or ""

    @pydantic.field_validator("type", mode="before")
    @classmethod
    def _type_default(cls, v):
        return v or "function"

    @pydantic.field_validator("function", mode="before")
    @classmethod
    def _function_default(cls, v):
        return v or {}


class LLMMessageExtraContent(pydantic.BaseModel):
    """
    saved run data carried on a message so historic turns can be exported with
    their originating run metadata. Never sent to the LLM.
    """

    model_config = pydantic.ConfigDict(extra="allow")

    display_content: str | None = None
    output_video: list[str] | None = None
    output_audio: list[str] | None = None


class LLMMessage(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="ignore")

    role: typing.Literal["system", "user", "assistant", "tool"] = CHATML_ROLE_USER
    content: str | list[dict] | None = None
    tool_calls: list[LLMToolCall] | None = None
    tool_call_id: str | None = None

    run_url: str | None = None
    extra_content: LLMMessageExtraContent | None = None

    @pydantic.field_validator("role", mode="before")
    @classmethod
    def _role_default(cls, v):
        return v or CHATML_ROLE_USER


def to_llm_body(
    messages: list[dict], *, model: AIModelSpec | None = None
) -> list[dict]:
    """Whitelist outgoing message fields so internal keys (chunk, run_url, extra_content, metrics, ...) don't cause HTTP 400s."""
    exclude = {"run_url": True, "extra_content": True}
    if not (model and model.is_google_model()):
        exclude["tool_calls"] = {"__all__": {"extra_content"}}
    return [
        LLMMessage.model_validate(entry).model_dump(
            exclude=exclude,
            exclude_none=True,
        )
        for entry in messages
    ]
