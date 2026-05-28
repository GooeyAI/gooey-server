from __future__ import annotations


from functions.base_llm_tool import (
    BaseLLMTool,
)

from bots.models import SavedRun

from daras_ai_v2.workflow_url_input import url_to_runs
from functions.gooey_builder_deploy_tool import DeployWorkflowLLMTool
from functions.gooey_builder_workflow_tools import (
    WORKFLOW_URL_KEY,
    FetchWorkflowStateLLMTool,
    UpdateWorkflowStateLLMTool,
    RunWorkflowLLMTool,
    SaveWorkflowLLMTool,
    SaveAsNewWorkflowLLMTool,
)
import gooey_gui as gui


def insert_gooey_builder_variables(state: dict, workflow_url: str):
    variables = state.setdefault("variables", {})
    variables[WORKFLOW_URL_KEY] = workflow_url

    variables_schema = state.setdefault("variables_schema", {})
    variables_schema[WORKFLOW_URL_KEY] = {"role": "system"}


def get_current_builder_tools(builder_sr: SavedRun) -> dict[str, BaseLLMTool]:
    workflow_url = gui.session_state.get("variables", {}).get(WORKFLOW_URL_KEY, "")
    if not workflow_url:
        return {}
    page_cls, sr, pr = url_to_runs(workflow_url)
    tools = [
        FetchWorkflowStateLLMTool(page_cls),
        UpdateWorkflowStateLLMTool(page_cls, sr, pr, builder_sr),
        RunWorkflowLLMTool(page_cls, sr, pr, builder_sr),
        SaveWorkflowLLMTool(page_cls, sr, pr, builder_sr),
        SaveAsNewWorkflowLLMTool(page_cls, sr, pr, builder_sr),
        DeployWorkflowLLMTool(page_cls, sr, pr, builder_sr),
    ]
    return {tool.name: tool for tool in tools}
