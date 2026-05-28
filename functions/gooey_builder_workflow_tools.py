from __future__ import annotations

from bots.models.published_run import PublishedRun
from bots.models import WorkflowAccessLevel, PublishedRun, SavedRun
import typing

from app_users.models import AppUser
from daras_ai_v2.crypto import get_random_doc_id
from functions.base_llm_tool import (
    BaseLLMTool,
)

from daras_ai_v2.base import BasePage, extract_model_fields

from daras_ai_v2.workflow_url_input import url_to_runs
import gooey_gui as gui

import json
from fastapi.encoders import jsonable_encoder

from workspaces.models import Workspace

WORKFLOW_URL_KEY = "builder_workflow_url"


class FetchWorkflowStateLLMTool(BaseLLMTool):
    disable_dynamic_loader = True

    name = "fetch_workflow_state"

    def __init__(self, page_cls: typing.Type[BasePage]):
        self.page_cls = page_cls
        super().__init__(
            name=self.name,
            label="Fetch Workflow State",
            description="Fetch the current state of a workflow",
            properties={"run_url": {"type": "string"}},
        )

    def call(self, run_url: str) -> typing.Any:
        from daras_ai_v2.workflow_url_input import url_to_runs

        page_cls, sr, pr = url_to_runs(run_url)
        ret = dict(success=True, state=sr.state)

        # if the fethed workflow is different from the current workflow,
        # add instructions to use the correct schema when updating the state
        if page_cls != self.page_cls:
            ret.update(
                dict(
                    instruction=f"You must use the given schema properties when using {UpdateWorkflowStateLLMTool.name}",
                    properties=page_cls.get_tool_call_schema(sr.state),
                )
            )

        return ret


class GooeyBuilderLLMTool(BaseLLMTool):
    disable_dynamic_loader = True

    page_cls: typing.Type[BasePage]
    sr: SavedRun
    pr: PublishedRun
    builder_sr: SavedRun

    def handle_redirect(self, background: bool):
        if background:
            return

        self.builder_sr.redirect_url = self.url
        self.builder_sr.save(update_fields=["redirect_url"])

        variables = gui.session_state.setdefault("variables", {})
        variables[WORKFLOW_URL_KEY] = self.url

    def get_current_runs(
        self, run_url: str | None
    ) -> tuple[typing.Type[BasePage], SavedRun, PublishedRun]:
        if run_url:
            return url_to_runs(run_url)
        else:
            return self.page_cls, self.sr, self.pr

    def get_current_user(self) -> AppUser:
        return AppUser.objects.get(uid=self.builder_sr.uid)

    def get_current_workspace(self) -> Workspace:
        return self.builder_sr.workspace

    def should_create_new_runs(self, run_url: str | None, sr: SavedRun) -> str | bool:
        return run_url or sr.parent_builder_saved_run_id != self.builder_sr.id


BACKGROUND_PROP = {
    "type": "boolean",
    "description": (
        "Whether to run this in the background. Useful for background/automation cases, "
        "batch or multi-run operations, parallel tool calls, diagnostics, retries."
    ),
    "default": False,
}


class UpdateWorkflowStateLLMTool(GooeyBuilderLLMTool):
    name = "update_workflow_state"

    def __init__(
        self,
        page_cls: typing.Type[BasePage],
        sr: SavedRun,
        pr: PublishedRun,
        builder_sr: SavedRun,
    ):
        self.page_cls = page_cls
        self.sr = sr
        self.pr = pr
        self.builder_sr = builder_sr

        state = sr.state

        properties = page_cls.get_tool_call_schema(state)
        properties.update(
            {
                "run_url": {
                    "type": "string",
                    "description": "(optional) The run_url of the workflow to update. Defaults to the current workflow.",
                },
                "background": BACKGROUND_PROP,
            }
        )

        current_workflow_state = dict(
            request=extract_model_fields(page_cls.RequestModel, state),
            response=extract_model_fields(page_cls.ResponseModel, state),
        )
        description = (
            "Call this tool to update the current workflow state without running it.\n\n"
            f"Once updated you can run the udpated workflow by calling the `{RunWorkflowLLMTool.name}` tool.\n"
            "By default, this tool will update the current workflow state. "
            f"You may call `{FetchWorkflowStateLLMTool.name}` to get the state of any workflow given its run_url "
            "and then call this tool with the run_url to update.\n\n"
            f"Current Workflow State: {json.dumps(jsonable_encoder(current_workflow_state))}"
        )
        super().__init__(
            name=self.name,
            label="Update Workflow State",
            description=description,
            properties=properties,
        )

    def call(
        self, run_url: str | None = None, background: bool = False, **request
    ) -> typing.Any:
        page_cls, sr, pr = self.get_current_runs(run_url)
        should_create_new_runs = self.should_create_new_runs(run_url, sr)

        if should_create_new_runs:
            sr = sr.clone(
                parent_pr=pr,
                uid=self.builder_sr.uid,
                workspace_id=self.builder_sr.workspace_id,
            )

        # update the state
        sr.state.update(request)
        # clear outputs
        for field_name in page_cls.ResponseModel.model_fields:
            sr.state.pop(field_name, None)
        sr.parent_builder_saved_run = self.builder_sr

        if sr.id:
            update_fields = ("state", "updated_at", "parent_builder_saved_run")
        else:
            update_fields = None
        sr.save(update_fields=update_fields)

        self.url = sr.get_app_url()
        if should_create_new_runs:
            self.handle_redirect(background)

        return dict(success=True, run_url=self.url)


class RunWorkflowLLMTool(GooeyBuilderLLMTool):
    name = "run_workflow"

    def __init__(
        self,
        page_cls: typing.Type[BasePage],
        sr: SavedRun,
        pr: PublishedRun,
        builder_sr: SavedRun,
    ):
        self.page_cls = page_cls
        self.sr = sr
        self.pr = pr
        self.builder_sr = builder_sr
        super().__init__(
            name=self.name,
            label="Run Workflow",
            description="Submit and Run the workflow",
            properties={
                "run_url": {
                    "type": "string",
                    "description": "(optional) The url of the workflow to run. Defaults to the current workflow.",
                },
                "background": BACKGROUND_PROP,
            },
        )

    def call(self, run_url: str | None = None, background: bool = False) -> typing.Any:
        page_cls, sr, pr = self.get_current_runs(run_url)
        user = self.get_current_user()

        if self.should_create_new_runs(run_url, sr):
            workspace = self.get_current_workspace()
            result, sr = sr.submit_api_call(
                current_user=user,
                workspace=workspace,
                request_body={},
                enable_rate_limits=True,
                parent_builder_saved_run=self.builder_sr,
                parent_pr=pr,
            )
        else:
            page = page_cls(user=user)
            result = page.call_runner_task(sr)

        self.url = sr.get_app_url()
        self.handle_redirect(background)

        sr.wait_for_celery_result(result)
        response = extract_model_fields(page_cls.ResponseModel, sr.state)
        if sr.error_msg:
            return dict(
                error=dict(
                    msg=sr.error_msg,
                    code=sr.error_code,
                    params=sr.error_params,
                    type=sr.error_type,
                ),
                response=response,
            )
        else:
            return response


class SaveWorkflowLLMTool(GooeyBuilderLLMTool):
    name = "save_workflow"

    def __init__(
        self,
        page_cls: typing.Type[BasePage],
        sr: SavedRun,
        pr: PublishedRun,
        builder_sr: SavedRun,
    ):
        self.page_cls = page_cls
        self.sr = sr
        self.pr = pr
        self.builder_sr = builder_sr

        super().__init__(
            name=self.name,
            label="Save Workflow",
            description=(
                "Save changes to the current published workflow as a new version. "
                "Call this when the user asks to save, publish, or update the current workflow "
                "(including its title or description) in place. "
                "If the user wants to copy/duplicate/fork the workflow into a new one, "
                f"call `{SaveAsNewWorkflowLLMTool.name}` instead. "
                "Pass `run_url` to save a specific saved run "
                f"(e.g. the `run_url` returned by `{UpdateWorkflowStateLLMTool.name}`); "
                "otherwise the currently open workflow run is saved."
            ),
            properties={
                "title": {
                    "type": "string",
                    "title": "Title",
                    "description": (
                        "Optional new value for the 'Title' "
                        "field in the Save Workflow dialog. "
                        "Leave unset to keep the existing title.\n\n"
                        f"Current title: {self.pr.title}"
                    ),
                },
                "description": {
                    "type": "string",
                    "title": "Description",
                    "description": (
                        "Optional new value for the 'Description' "
                        "field in the Save Workflow dialog "
                        "Leave unset to keep the existing description.\n\n"
                        f"Current description: {self.pr.notes}"
                    ),
                },
                "change_notes": {
                    "type": "string",
                    "title": "Add change notes",
                    "description": "Used as the changelog entry for the new version.\n\n"
                    f"Last change notes: {self.sr.parent_version and self.sr.parent_version.change_notes}",
                },
                "run_url": {
                    "type": "string",
                    "description": "(optional) The url of the workflow to save. Defaults to the current workflow.",
                },
                "background": BACKGROUND_PROP,
            },
        )

    def call(
        self,
        title: str | None = None,
        description: str | None = None,
        change_notes: str = "",
        run_url: str | None = None,
        background: bool = False,
    ) -> dict:
        page_cls, sr, pr = self.get_current_runs(run_url)
        user = self.get_current_user()
        workspace = self.get_current_workspace()

        if pr.is_root():
            return dict(error="You can't update the root workflow")

        if not WorkflowAccessLevel.can_user_edit_published_run(
            workspace=workspace, user=user, pr=pr
        ):
            return dict(
                error=(
                    "You don't have permission to update this workflow. "
                    f"Call `{SaveAsNewWorkflowLLMTool.name}` instead."
                )
            )

        pr.add_version(
            user=user,
            saved_run=sr,
            title=title or pr.title,
            notes=description or pr.notes,
            change_notes=change_notes,
            # photo_url=photo_url,
            # tags=tags,
        )
        self.url = pr.get_app_url()
        self.handle_redirect(background)
        return dict(success=True, run_url=self.url)


class SaveAsNewWorkflowLLMTool(GooeyBuilderLLMTool):
    name = "save_as_new_workflow"

    def __init__(
        self,
        page_cls: typing.Type[BasePage],
        sr: SavedRun,
        pr: PublishedRun,
        builder_sr: SavedRun,
    ):
        self.page_cls = page_cls
        self.sr = sr
        self.pr = pr
        self.builder_sr = builder_sr

        super().__init__(
            name=self.name,
            label="Save as New Workflow",
            description=(
                "Create a new published workflow that is a copy of the current one. "
                "Call this when the user asks to save as new workflow, save as new version, duplicate, fork, clone, etc. "
                f"Use `{SaveWorkflowLLMTool.name}` instead if the user wants to update an existing workflow in place. "
            ),
            properties={
                "title": {
                    "type": "string",
                    "title": "Title",
                    "description": (
                        "(optional) title of the new workflow. "
                        'Defaults to the original title with " (Copy)" appended.'
                    ),
                },
                "description": {
                    "type": "string",
                    "title": "Description",
                    "description": (
                        "(Optional) description of the new workflow. "
                        "Defaults to the original description."
                    ),
                },
                "run_url": {
                    "type": "string",
                    "description": (
                        "(optional) The url of the workflow to save as new. "
                        "Defaults to the current workflow."
                    ),
                },
                "background": BACKGROUND_PROP,
            },
        )

    def call(
        self,
        title: str | None = None,
        description: str | None = None,
        run_url: str | None = None,
        background: bool = False,
    ) -> dict:
        page_cls, sr, pr = self.get_current_runs(run_url)
        user = self.get_current_user()
        workspace = self.get_current_workspace()

        new_title = (title or pr.title).strip()
        if not title and new_title == pr.title:
            new_title = f"{new_title} (Copy)"
        new_notes = (description if description is not None else pr.notes).strip()

        new_pr = self.page_cls.create_published_run(
            published_run_id=get_random_doc_id(),
            saved_run=sr,
            user=user,
            workspace=workspace,
            tags=list(pr.tags.all()),
            title=new_title,
            notes=new_notes,
        )
        self.url = new_pr.get_app_url()
        self.handle_redirect(background)
        return dict(success=True, run_url=self.url)
