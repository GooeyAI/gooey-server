from types import SimpleNamespace

import pytest

from ai_models.models import AIModelSpec, ModelProvider
from daras_ai_v2 import language_model
from usage_costs.models import ModelSku


@pytest.mark.parametrize(
    ("model", "api_key", "api_base", "extra"),
    [
        (
            "anthropic/claude-sonnet-4-5",
            "test-key",
            "https://example.com/v1",
            {"api_key": "test-key", "api_base": "https://example.com/v1"},
        ),
        ("anthropic/claude-sonnet-4-5", "", "", {}),
        (
            "vertex_ai/gemini-3.6-flash",
            "",
            "",
            {"vertex_location": "global"},
        ),
    ],
)
def test_get_responses_create_uses_litellm(
    monkeypatch, model, api_key, api_base, extra
):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    calls = []

    def responses(**kwargs):
        calls.append(kwargs)
        return "response"

    monkeypatch.setattr("litellm.responses", responses)

    create = language_model._get_responses_create(
        provider=ModelProvider.litellm_responses,
        model=model,
        api_key=api_key,
        base_url=api_base,
        messages=[{"role": "user", "content": "Hello"}],
        stream=False,
        max_output_tokens=100,
    )

    assert create() == ("response", model)
    assert calls == [
        {
            "model": model,
            "input": [{"role": "user", "content": "Hello"}],
            "stream": False,
            "max_output_tokens": 100,
        }
        | extra
    ]


def test_run_openai_responses_accepts_litellm_response(monkeypatch):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    from litellm.types.llms.openai import ResponsesAPIResponse

    response = ResponsesAPIResponse(
        id="response-id",
        created_at=0,
        output=[
            {
                "type": "message",
                "id": "message-id",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Hello from LiteLLM",
                        "annotations": [],
                    }
                ],
            }
        ],
        usage={"input_tokens": 4, "output_tokens": 5, "total_tokens": 9},
    )
    create_calls = []
    cost_calls = []

    def get_responses_create(**kwargs):
        create_calls.append(kwargs)
        return lambda: (response, kwargs["model"])

    monkeypatch.setattr(language_model, "_get_responses_create", get_responses_create)
    monkeypatch.setattr(
        "usage_costs.cost_utils.record_cost_auto",
        lambda **kwargs: cost_calls.append(kwargs),
    )

    result = language_model.run_openai_responses(
        model=AIModelSpec(
            name="test_model",
            label="Test model",
            model_id="anthropic/claude-sonnet-4-5",
            provider=ModelProvider.litellm_responses,
        ),
        messages=[{"role": "user", "content": "Hello"}],
        max_output_tokens=100,
        start_chunk_size=1,
        stop_chunk_size=10,
        step_chunk_size=1,
    )

    assert result == [{"role": "assistant", "content": "Hello from LiteLLM"}]
    assert create_calls[0]["provider"] == ModelProvider.litellm_responses
    assert cost_calls == [
        {
            "model": "anthropic/claude-sonnet-4-5",
            "sku": ModelSku.llm_prompt,
            "quantity": 4,
        },
        {
            "model": "anthropic/claude-sonnet-4-5",
            "sku": ModelSku.llm_completion,
            "quantity": 5,
        },
    ]


def test_stream_openai_responses_accepts_litellm_events(monkeypatch):
    response = SimpleNamespace(usage=SimpleNamespace(input_tokens=4, output_tokens=3))
    events = [
        SimpleNamespace(type="response.output_text.delta", delta="Hello world"),
        SimpleNamespace(type="response.output_text.done"),
        SimpleNamespace(type="response.completed", response=response),
    ]
    record_usage = []
    monkeypatch.setattr(
        language_model,
        "record_openai_llm_usage",
        lambda *args: record_usage.append(args),
    )

    chunks = list(
        language_model._stream_openai_responses(
            events,
            "anthropic/claude-sonnet-4-5",
            [{"role": "user", "content": "Hello"}],
            start_chunk_size=100,
            stop_chunk_size=100,
            step_chunk_size=1,
        )
    )

    assert chunks[-1][0]["content"] == "Hello world"
    assert record_usage[0][1] is response
