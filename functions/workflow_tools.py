from __future__ import annotations

import json
import textwrap
import typing

from django.utils.text import slugify

from app_users.models import AppUser
from daras_ai_v2.exceptions import UserError
from functions.gooey_builder_tools import UpdateGuiStateLLMTool
from functions.inbuilt_tools import (
    FeedbackCollectionLLMTool,
    VectorSearchLLMTool,
    CallTransferLLMTool,
)
from functions.models import CalledFunction, FunctionTrigger
from functions.base_llm_tool import (
    BaseLLMTool,
    generate_tool_properties,
    get_external_tool_slug_from_url,
)


if typing.TYPE_CHECKING:
    from bots.models import SavedRun
    from daras_ai_v2.base import BasePage
    from workspaces.models import Workspace

DYNAMIC_TOOL_SEARCH_THRESHOLD = 20_000


class WorkflowLLMTool(BaseLLMTool):
    """External function tool that calls workflow URLs."""

    def __init__(self, function_url: str):
        from bots.models import Workflow
        from daras_ai_v2.base import extract_model_fields
        from daras_ai_v2.workflow_url_input import url_to_runs

        self.function_url = function_url

        self.page_cls, self.fn_sr, self.fn_pr = url_to_runs(function_url)
        self._fn_runs = (self.fn_sr, self.fn_pr)

        self.name = slugify(self.fn_pr.title).replace("-", "_")

        self.is_function_workflow = self.fn_sr.workflow == Workflow.FUNCTIONS
        if self.is_function_workflow:
            fn_vars = self.fn_sr.state.get("variables", {})
            fn_vars_schema = self.fn_sr.state.get("variables_schema", {})
            properties = dict(generate_tool_properties(fn_vars, fn_vars_schema))
        else:
            fn_vars = extract_model_fields(self.page_cls.RequestModel, self.fn_sr.state)
            properties = self.page_cls.get_tool_call_schema(self.fn_sr.state)

        super().__init__(
            name=self.name,
            label=self.fn_pr.title or self.name,
            description=self._build_workflow_description(fn_vars),
            properties=properties,
        )

    def bind(
        self,
        saved_run: SavedRun,
        workspace: Workspace,
        current_user: AppUser,
        request_model: typing.Type[BasePage.RequestModel],
        response_model: typing.Type[BasePage.ResponseModel],
        state: dict,
        trigger: FunctionTrigger,
    ) -> "WorkflowLLMTool":
        self.saved_run = saved_run
        self.workspace = workspace
        self.current_user = current_user
        self.request_model = request_model
        self.response_model = response_model
        self.state = state
        self.trigger = trigger
        return self

    def call(self, **kwargs):
        from bots.models import Workflow
        from daras_ai_v2.base import extract_model_fields

        try:
            self.saved_run
        except AttributeError:
            raise RuntimeError(f"This {self.__class__} instance is not yet bound")

        fn_sr, fn_pr = self._fn_runs

        if fn_sr.workflow == Workflow.FUNCTIONS:
            state_vars = self.state.setdefault("variables", {})
            state_vars_schema = self.state.setdefault("variables_schema", {})
            system_vars, system_vars_schema = self._get_system_vars()
            request_body = dict(
                variables=(
                    (fn_sr.state.get("variables") or {})
                    | state_vars
                    | system_vars
                    | kwargs
                ),
                variables_schema=(
                    (fn_sr.state.get("variables_schema") or {})
                    | state_vars_schema
                    | system_vars_schema
                ),
            )
            memory_scope = self._get_gooey_memory_tool_scope_name()
            if memory_scope:
                request_body["memory_scope"] = memory_scope
        else:
            request_body = kwargs

        called_fn = CalledFunction(
            saved_run=self.saved_run,
            trigger=self.trigger.db_value,
            tool_name=self.name,
        )
        result, fn_sr = fn_sr.submit_api_call(
            workspace=self.workspace,
            current_user=self.current_user,
            parent_pr=fn_pr,
            request_body=request_body,
            deduct_credits=False,
            called_fn=called_fn,
        )
        self.fn_sr = fn_sr

        # wait for the result if its a pre request function
        if self.trigger == FunctionTrigger.post:
            return
        fn_sr.wait_for_celery_result(result)
        # if failed, bubble up error so the parent run's standard error pipeline renders it
        if fn_sr.error_msg:
            raise CalledFunctionError(
                message=fn_sr.error_msg,
                status_code=fn_sr.error_code,
                error_params=fn_sr.error_params,
                error_type=fn_sr.error_type,
            )

        if fn_sr.workflow != Workflow.FUNCTIONS:
            page_cls = Workflow(fn_sr.workflow).page_cls
            return_value = extract_model_fields(page_cls.ResponseModel, fn_sr.state)
            return return_value

        # save the output from the function
        return_value = fn_sr.state.get("return_value")
        if return_value is not None:
            if isinstance(return_value, dict):
                for k, v in return_value.items():
                    if (
                        k in self.request_model.model_fields
                        or k in self.response_model.model_fields
                    ):
                        self.state[k] = v
                    else:
                        state_vars[k] = v
                        state_vars_schema[k] = {"role": "system"}
            else:
                state_vars["return_value"] = return_value
                state_vars_schema["return_value"] = {"role": "system"}

        return dict(
            return_value=return_value,
            error=fn_sr.state.get("error"),
            logs=fn_sr.state.get("logs"),
        )

    def _get_gooey_memory_tool_scope_name(self) -> str | None:
        from functions.memory_tools import (
            GooeyMemoryLLMToolDelete,
            GooeyMemoryLLMToolRead,
            GooeyMemoryLLMToolWrite,
        )

        functions = self.state.get("functions") or []
        memory_tool_names = {
            GooeyMemoryLLMToolRead.name,
            GooeyMemoryLLMToolWrite.name,
            GooeyMemoryLLMToolDelete.name,
        }
        for function in functions:
            url = function.get("url")
            if not url:
                continue
            tool_slug = get_external_tool_slug_from_url(url)
            if tool_slug in memory_tool_names:
                return function.get("scope")
        return None

    def _build_workflow_description(self, fn_vars: dict) -> str:
        description = (
            self.fn_pr.notes
            + "\n\nDon't override default function parameters unless explicitly requested. "
        )
        params = [f"{k} = {json.dumps(v)}" for k, v in fn_vars.items()]
        return render_fn_pseudocode(self.name, description, params)

    def _get_system_vars(self) -> tuple[dict, dict]:
        request = self.request_model.model_validate(self.state)
        system_vars = dict(
            web_url=self.saved_run.get_app_url(),
            request=request.model_dump(
                exclude_unset=True, exclude={"variables"}, mode="json"
            ),
            response={
                k: v
                for k, v in self.state.items()
                if k in self.response_model.model_fields
            },
        )
        system_vars_schema = {var: {"role": "system"} for var in system_vars}

        return system_vars, system_vars_schema

    def get_icon(self) -> str:
        if self.fn_pr and self.fn_pr.photo_url:
            return self.fn_pr.photo_url

        # Fallback to workflow emoji
        from bots.models import WorkflowMetadata

        try:
            workflow_meta = WorkflowMetadata.objects.get(workflow=self.fn_sr.workflow)
            return workflow_meta.emoji
        except WorkflowMetadata.DoesNotExist:
            return ""

    def get_url(self) -> str:
        return self.fn_sr.get_app_url()


class CalledFunctionError(UserError):
    def __init__(
        self,
        message: str,
        status_code: int,
        error_params: dict | None,
        error_type: str | None,
    ):
        self.error_type = error_type
        super().__init__(
            message=message, status_code=status_code, error_params=error_params
        )


class DynamicLLMToolLoader(BaseLLMTool):
    name = "load_tools"

    def __init__(
        self, available_tools: dict[str, BaseLLMTool], active_tool_names: set[str]
    ):
        self.available_tools = available_tools
        self.active_tool_names = active_tool_names

        # enable tool search if the appx size of tool specs exceeds a certain threshold
        self.enabled = (
            sum(
                len(json.dumps(tool.spec_function))
                for tool in self.available_tools.values()
            )
            > DYNAMIC_TOOL_SEARCH_THRESHOLD
        )
        if not self.enabled:
            super().__init__(name=self.name, label="", description="", properties={})
            return

        searchable_tools = [
            tool for tool in available_tools.values() if not self.is_tool_active(tool)
        ]

        tool_catalog = "\n\n".join(
            _render_tool_catalog_entry(tool) for tool in searchable_tools
        )
        description = (
            f"You MUST call `{self.name}` to fetch the JSON schema for any tool before calling it. "
            "If a task needs multiple tools, request all of them in a single call."
            f"\n\nAvailable tools:\n\n{tool_catalog}\n\n"
            "These stubs are only a hint. "
            f"Always refer to the actual JSON schema returned by `{self.name}` "
            "for the most up-to-date and accurate information about the tools, as they may change over time. "
        )

        searchable_tool_names = sorted(tool.name for tool in searchable_tools)

        super().__init__(
            name=self.name,
            label="Load Tools",
            description=description,
            properties={
                "tool_names": {
                    "type": "array",
                    "description": "One or more exact tool names from the list above.",
                    "items": {
                        "type": "string",
                        "enum": searchable_tool_names,
                    },
                }
            },
            required=["tool_names"],
        )

    def call(self, tool_names: list[str]) -> dict:
        missing = []
        for tool_name in tool_names:
            if tool_name in self.available_tools:
                self.active_tool_names.add(tool_name)
            else:
                missing.append(tool_name)
        ret = {"loaded_tools": list(self.active_tool_names)}
        if missing:
            ret["missing_tools"] = missing
        return ret

    def is_tool_active(self, tool: BaseLLMTool) -> bool:
        if self.enabled:
            return (
                tool.name in self.active_tool_names
                or tool.name == self.name
                or isinstance(tool, self.excluded_tools)
            )
        else:
            return tool.name != self.name

    excluded_tools = (
        CallTransferLLMTool,
        VectorSearchLLMTool,
        FeedbackCollectionLLMTool,
        UpdateGuiStateLLMTool,
    )


def _render_tool_catalog_entry(tool: BaseLLMTool) -> str:
    if isinstance(tool, WorkflowLLMTool):
        description = tool.fn_pr.notes
    else:
        description = tool.description or tool.label

    param_names = list(tool.spec_parameters.get("properties", {}))
    return render_fn_pseudocode(tool.name, description, param_names)


def render_fn_pseudocode(name: str, description: str, params: list[str]) -> str:
    description = textwrap.indent(description, " * ", predicate=lambda line: True)
    params_str = ", ".join(params)
    return "/**\n" + description + "\n */\n" + name + "({ " + params_str + " });"
