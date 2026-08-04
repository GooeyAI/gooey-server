from __future__ import annotations

import gooey_gui as gui
from bots.models import SavedRun
from daras_ai_v2.workflow_url_input import url_to_runs
from functions.base_llm_tool import (
    BaseLLMTool,
)
from functions.gooey_builder_deploy_tool import DeployWorkflowLLMTool
from functions.gooey_builder_workflow_tools import (
    WORKFLOW_URL_KEY,
    FetchWorkflowStateLLMTool,
    RunWorkflowLLMTool,
    SaveAsNewWorkflowLLMTool,
    SaveWorkflowLLMTool,
    SearchWorkflowsLLMTool,
    UpdateWorkflowStateLLMTool,
)


def insert_gooey_builder_variables(state: dict, workflow_url: str):
    variables = state.setdefault("variables", {})
    variables[WORKFLOW_URL_KEY] = workflow_url

    variables_schema = state.setdefault("variables_schema", {})
    variables_schema[WORKFLOW_URL_KEY] = {"role": "system"}


def get_current_builder_tools(builder_sr: SavedRun) -> dict[str, BaseLLMTool]:
    variables = gui.session_state.get("variables", {})
    try:
        workflow_url = variables[WORKFLOW_URL_KEY]
    except KeyError:
        return {}
    if workflow_url:
        page_cls, sr, pr = url_to_runs(workflow_url)
    else:
        page_cls, sr, pr = None, None, None
    tools = [
        SearchWorkflowsLLMTool(builder_sr.uid),
        FetchWorkflowStateLLMTool(page_cls),
        UpdateWorkflowStateLLMTool(page_cls, sr, pr, builder_sr),
        RunWorkflowLLMTool(page_cls, sr, pr, builder_sr),
        SaveWorkflowLLMTool(page_cls, sr, pr, builder_sr),
        SaveAsNewWorkflowLLMTool(page_cls, sr, pr, builder_sr),
    ]
    if workflow_url:
        tools += [
            DeployWorkflowLLMTool(page_cls, sr, pr, builder_sr),
        ]
    return {tool.name: tool for tool in tools}
