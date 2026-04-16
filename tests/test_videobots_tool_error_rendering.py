from types import MethodType, SimpleNamespace

import pytest

from functions.inbuilt_tools import LoadToolsLLMTool
from functions.recipe_functions import BaseLLMTool
from recipes.VideoBots import VideoBotsPage


class FailingTool(BaseLLMTool):
    icon = "🔥"

    def __init__(self):
        super().__init__(
            name="failing_tool",
            label="Failing Tool",
            description="Tool that always fails.",
            properties={},
        )
        self.url = "https://example.com/runs/child"

    def call(self, **kwargs):
        raise RuntimeError("tool exploded")


def test_llm_loop_records_failed_tool_output_with_run_url(monkeypatch):
    def fake_run_language_model(**kwargs):
        yield [
            {
                "content": "Calling the tool now.",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "function": {
                            "name": "failing_tool",
                            "arguments": "{}",
                        },
                    }
                ],
                "finish_reason": "tool_calls",
            }
        ]

    def fake_output_translation_step(self, request, response, output_text):
        if False:
            yield None
        return output_text

    monkeypatch.setattr("recipes.VideoBots.run_language_model", fake_run_language_model)

    page = VideoBotsPage.__new__(VideoBotsPage)
    page.output_translation_step = MethodType(fake_output_translation_step, page)
    page._update_searched_tool_names = MethodType(
        lambda self, tool, arguments: None, page
    )

    request = SimpleNamespace(
        max_tokens=100,
        num_outputs=1,
        sampling_temperature=0,
        avoid_repetition=False,
        response_format_type=None,
        reasoning_effort=None,
        input_audio=None,
        openai_voice_name=None,
    )
    response = VideoBotsPage.ResponseModel(
        final_prompt=[], output_text=[], output_audio=[]
    )
    model = SimpleNamespace(
        name="gpt_4_o_mini",
        label="GPT-4o Mini",
        llm_is_audio_model=False,
    )
    tool = FailingTool()

    page._active_tool_names = {tool.name}

    with pytest.raises(RuntimeError, match="tool exploded"):
        list(
            page.llm_loop(
                request=request,
                response=response,
                model=model,
                tools_by_name={tool.name: tool},
            )
        )

    assert response.final_prompt[-1]["role"] == "tool"
    assert response.final_prompt[-1]["tool_call_id"] == "call_123"
    assert response.final_prompt[-1]["run_url"] == "https://example.com/runs/child"
    assert "tool exploded" in response.final_prompt[-1]["content"]


def test_llm_loop_uses_active_tools_for_load_tools_metadata(monkeypatch):
    active_tool_names = set()
    LoadToolsLLMTool({"failing_tool": FailingTool()}, active_tool_names)
    calls = 0

    def fake_run_language_model(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield [
                {
                    "content": "Loading the tool schema.",
                    "tool_calls": [
                        {
                            "id": "call_search",
                            "function": {
                                "name": "load_tools",
                                "arguments": '{"tool_names":["failing_tool"]}',
                            },
                        }
                    ],
                    "finish_reason": "tool_calls",
                }
            ]
            return

        yield [
            {
                "content": "Schema loaded.",
                "finish_reason": "stop",
            }
        ]

    def fake_output_translation_step(self, request, response, output_text):
        if False:
            yield None
        return output_text

    monkeypatch.setattr("recipes.VideoBots.run_language_model", fake_run_language_model)

    page = VideoBotsPage.__new__(VideoBotsPage)
    page.output_translation_step = MethodType(fake_output_translation_step, page)
    page._active_tool_names = active_tool_names

    request = SimpleNamespace(
        max_tokens=100,
        num_outputs=1,
        sampling_temperature=0,
        avoid_repetition=False,
        response_format_type=None,
        reasoning_effort=None,
        input_audio=None,
        openai_voice_name=None,
    )
    response = VideoBotsPage.ResponseModel(
        final_prompt=[], output_text=[], output_audio=[]
    )
    model = SimpleNamespace(
        name="gpt_4_o_mini",
        label="GPT-4o Mini",
        llm_is_audio_model=False,
    )

    list(
        page.llm_loop(
            request=request,
            response=response,
            model=model,
            tools_by_name={"failing_tool": FailingTool()},
        )
    )

    assistant_entries = [
        entry for entry in response.final_prompt if entry.get("role") == "assistant"
    ]
    load_tools_calls = [
        call
        for entry in assistant_entries
        for call in entry.get("tool_calls", [])
        if call["function"]["name"] == "load_tools"
    ]

    assert load_tools_calls
    assert load_tools_calls[0]["label"] == "Load Tools"
    assert any(
        entry.get("role") == "tool" and entry.get("tool_call_id") == "call_search"
        for entry in response.final_prompt
    )


def test_load_tools_schema_enums_available_tool_names():
    from functions.composio_tools import ComposioLLMTool
    from functions.recipe_functions import WorkflowLLMTool

    workflow_tool = WorkflowLLMTool.__new__(WorkflowLLMTool)
    workflow_tool.name = "workflow_tool"
    workflow_tool.label = "Workflow Tool"
    workflow_tool.description = "Loaded workflow tool."
    workflow_tool.catalog_description = "Catalog workflow tool."
    workflow_tool.spec_parameters = {
        "properties": {
            "workflow_arg": {"type": "string"},
            "other_arg": {"type": "number"},
        }
    }

    composio_tool = ComposioLLMTool.__new__(ComposioLLMTool)
    composio_tool.name = "composio_tool"
    composio_tool.label = "Composio Tool"
    composio_tool.description = "Loaded composio tool."
    composio_tool.spec_parameters = {"properties": {}}

    load_tools = LoadToolsLLMTool(
        {
            "workflow_tool": workflow_tool,
            "composio_tool": composio_tool,
            "failing_tool": FailingTool(),
        },
        set(),
    )

    assert load_tools.spec_parameters["properties"]["tool_names"]["items"]["enum"] == [
        "composio_tool",
        "workflow_tool",
    ]
    assert "`composio_tool`" in load_tools.description
    assert "params: none" in load_tools.description
    assert "workflow_tool" in load_tools.description
    assert "params: `workflow_arg`, `other_arg`" in load_tools.description
