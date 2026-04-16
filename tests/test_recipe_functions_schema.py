from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from ai_models.models import AIModelSpec
from recipes.DocExtract import DocExtractPage
from recipes.DocSearch import DocSearchPage
from recipes.DocSummary import DocSummaryPage
from recipes.CompareLLM import CompareLLMPage
from recipes.GoogleGPT import GoogleGPTPage
from recipes.SEOSummary import SEOSummaryPage
from recipes.SmartGPT import SmartGPTPage
from recipes.SocialLookupEmail import SocialLookupEmailPage
from recipes.VideoBots import VideoBotsPage
from functions.recipe_functions import WorkflowLLMTool, get_json_type


class FakeRequestModel(BaseModel):
    should_search: bool | None = None
    search_query: str | None = None


class FakePage:
    RequestModel = FakeRequestModel

    @classmethod
    def get_example_preferred_fields(cls, state: dict) -> list[str]:
        return ["search_query"]

    @classmethod
    def get_example_request(
        cls,
        state: dict,
        pr=None,
        include_all: bool = False,
    ) -> tuple[None, dict]:
        cls.last_include_all = include_all
        return None, {
            "should_search": True,
            "search_query": "weather in sf",
        }


def test_get_json_type_prefers_boolean_over_number():
    assert get_json_type(True) == "boolean"


def test_workflow_llm_tool_description_guides_sparse_updates(monkeypatch):
    from daras_ai_v2 import workflow_url_input

    monkeypatch.setattr(
        workflow_url_input,
        "url_to_runs",
        lambda function_url: (
            FakePage,
            SimpleNamespace(workflow="not-functions", state={}),
            SimpleNamespace(title="Demo Workflow", notes="Original notes."),
        ),
    )

    tool = WorkflowLLMTool("https://example.com/workflow")

    assert "required" not in tool.spec_parameters
    assert set(tool.spec_parameters["properties"]) == {
        "should_search",
        "search_query",
    }
    assert tool.spec_parameters["properties"]["should_search"]["type"] == "object"
    assert (
        "Use default parameters unless explicitly requested."
        in tool.spec_function["description"]
    )
    assert (
        "demo_workflow({ should_search = null, search_query = null });"
        in tool.spec_function["description"]
    )
    assert (
        "It's a bad programming practice if argument equals to the default parameter value."
        in tool.spec_function["description"]
    )


def test_workflow_llm_tool_description_includes_current_values(monkeypatch):
    from daras_ai_v2 import workflow_url_input

    monkeypatch.setattr(
        workflow_url_input,
        "url_to_runs",
        lambda function_url: (
            FakePage,
            SimpleNamespace(workflow="not-functions", state={}),
            SimpleNamespace(title="Demo Workflow", notes="Original notes."),
        ),
    )

    tool = WorkflowLLMTool("https://example.com/workflow")

    assert (
        "demo_workflow({ should_search = null, search_query = null });"
        in tool.spec_function["description"]
    )


def test_workflow_llm_tool_uses_update_gui_state_schema_for_nested_objects(
    monkeypatch,
):
    from daras_ai_v2 import workflow_url_input

    class FakeVideoRequestModel(BaseModel):
        selected_models: list[str]
        inputs: dict[str, object]

    class FakeVideoPage:
        RequestModel = FakeVideoRequestModel

        @classmethod
        def get_example_preferred_fields(cls, state: dict) -> list[str]:
            return []

        @classmethod
        def get_update_gui_state_schema(cls, builder_state: dict) -> dict[str, object]:
            return {
                "selected_models": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "inputs": {
                    "type": "object",
                    "properties": {
                        "seed": {"type": "number"},
                        "prompt": {"type": "string"},
                    },
                },
            }

    state = {
        "selected_models": ["veo-3"],
        "inputs": {
            "seed": 0,
            "prompt": "hello world",
        },
    }

    monkeypatch.setattr(
        workflow_url_input,
        "url_to_runs",
        lambda function_url: (
            FakeVideoPage,
            SimpleNamespace(workflow="not-functions", state=state),
            SimpleNamespace(title="Generate Video", notes="Original notes."),
        ),
    )

    tool = WorkflowLLMTool("https://example.com/video")

    assert tool.spec_parameters["properties"]["inputs"] == {
        "description": "",
        "type": "object",
        "properties": {
            "seed": {"type": "number"},
            "prompt": {"type": "string"},
        },
    }


@pytest.mark.django_db
def test_get_llms_for_frontend_includes_selected_deprecated_models():
    current_model = AIModelSpec.objects.create(
        name="queryset-llm-current",
        label="Current LLM",
        model_id="queryset-llm-current",
        category=AIModelSpec.Categories.llm,
    )
    deprecated_model = AIModelSpec.objects.create(
        name="queryset-llm-deprecated",
        label="Deprecated LLM",
        model_id="queryset-llm-deprecated",
        category=AIModelSpec.Categories.llm,
        is_deprecated=True,
    )

    llm_names = set(
        AIModelSpec.objects.get_llms_for_frontend(
            selected_models=deprecated_model.name
        ).values_list("name", flat=True)
    )

    assert llm_names >= {
        current_model.name,
        deprecated_model.name,
    }


@pytest.mark.django_db
def test_videobots_tool_call_schema_uses_dynamic_selected_model_enum():
    current_model = AIModelSpec.objects.create(
        name="llm-current",
        label="Current LLM",
        model_id="llm-current",
        category=AIModelSpec.Categories.llm,
    )
    deprecated_model = AIModelSpec.objects.create(
        name="llm-deprecated",
        label="Deprecated LLM",
        model_id="llm-deprecated",
        category=AIModelSpec.Categories.llm,
        is_deprecated=True,
    )

    schema = VideoBotsPage.get_tool_call_schema(
        {
            "selected_model": deprecated_model.name,
        }
    )

    selected_model_schema = schema["selected_model"]

    assert "type" not in selected_model_schema
    assert "enum" not in selected_model_schema
    assert selected_model_schema["default"] is None
    assert selected_model_schema["title"] == "Selected Model"
    assert selected_model_schema["anyOf"][1] == {"type": "null"}
    assert selected_model_schema["anyOf"][0]["type"] == "string"
    assert set(selected_model_schema["anyOf"][0]["enum"]) == {
        current_model.name,
        deprecated_model.name,
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    "page_cls",
    [
        VideoBotsPage,
        GoogleGPTPage,
        SEOSummaryPage,
        DocSummaryPage,
        SmartGPTPage,
        DocSearchPage,
        DocExtractPage,
        SocialLookupEmailPage,
    ],
)
def test_language_model_selector_recipes_use_dynamic_selected_model_enum(page_cls):
    current_model = AIModelSpec.objects.create(
        name=f"{page_cls.__name__}-llm-current",
        label="Current LLM",
        model_id=f"{page_cls.__name__}-llm-current",
        category=AIModelSpec.Categories.llm,
    )
    deprecated_model = AIModelSpec.objects.create(
        name=f"{page_cls.__name__}-llm-deprecated",
        label="Deprecated LLM",
        model_id=f"{page_cls.__name__}-llm-deprecated",
        category=AIModelSpec.Categories.llm,
        is_deprecated=True,
    )

    schema = page_cls.get_tool_call_schema({"selected_model": deprecated_model.name})

    selected_model_schema = schema["selected_model"]

    assert "type" not in selected_model_schema
    assert "enum" not in selected_model_schema
    assert selected_model_schema["default"] is None
    assert selected_model_schema["title"] == "Selected Model"
    assert selected_model_schema["anyOf"][1] == {"type": "null"}
    assert selected_model_schema["anyOf"][0]["type"] == "string"
    assert set(selected_model_schema["anyOf"][0]["enum"]) >= {
        current_model.name,
        deprecated_model.name,
    }


@pytest.mark.django_db
def test_compare_llm_tool_call_schema_uses_dynamic_selected_models_enum():
    current_model = AIModelSpec.objects.create(
        name="compare-llm-current",
        label="Current LLM",
        model_id="compare-llm-current",
        category=AIModelSpec.Categories.llm,
    )
    deprecated_model = AIModelSpec.objects.create(
        name="compare-llm-deprecated",
        label="Deprecated LLM",
        model_id="compare-llm-deprecated",
        category=AIModelSpec.Categories.llm,
        is_deprecated=True,
    )

    schema = CompareLLMPage.get_tool_call_schema(
        {"selected_models": [deprecated_model.name]}
    )

    selected_models_schema = schema["selected_models"]

    assert "type" not in selected_models_schema
    assert "items" not in selected_models_schema
    assert selected_models_schema["default"] is None
    assert selected_models_schema["title"] == "Selected Models"
    assert selected_models_schema["anyOf"][1] == {"type": "null"}
    assert selected_models_schema["anyOf"][0]["type"] == "array"
    assert selected_models_schema["anyOf"][0]["items"]["type"] == "string"
    assert set(selected_models_schema["anyOf"][0]["items"]["enum"]) >= {
        current_model.name,
        deprecated_model.name,
    }
