from __future__ import annotations

from bots.models import WorkflowAccessLevel, PublishedRun, SavedRun
import typing

from app_users.models import AppUser
from bots.models.workflow import Workflow
from daras_ai_v2.crypto import get_random_doc_id
from functions.base_llm_tool import (
    BaseLLMTool,
)

from daras_ai_v2.base import BasePage, extract_model_fields

from daras_ai_v2.workflow_url_input import url_to_runs
import gooey_gui as gui

import json
from fastapi.encoders import jsonable_encoder

from widgets.workflow_search import SearchFilters, get_filtered_published_runs
from workspaces.models import Workspace

WORKFLOW_URL_KEY = "builder_workflow_url"

MAX_SEARCH_RESULTS = 10


class SearchWorkflowsLLMTool(BaseLLMTool):
    disable_dynamic_loader = True

    name = "search_workflows"

    def __init__(self, uid: str):
        self.uid = uid
        super().__init__(
            name=self.name,
            label="Search Workflows",
            description=(
                "Search Gooey.AI's workflow library (same search as the /explore page) "
                "to find a workflow to use as the starting point for the user's request. "
                "This is a keyword (full-text) search, NOT semantic search: every word in "
                "the query must literally match the workflow's title/description/tags, so "
                "long free-form queries usually return nothing. "
                "Use 1-3 short generic keywords (e.g. 'image', 'lipsync', 'copilot') and "
                "broaden the query further if there are no results. "
            ),
            properties={
                "search": {
                    "type": "string",
                    "description": (
                        "Keyword search query. All words must match, so keep it to 1-3 "
                        "short keywords, e.g. 'image', 'lipsync video', 'qr code'. "
                        "Do NOT paste the user's full request here."
                    ),
                },
            },
            required=["search"],
        )

    def call(self, search: str) -> dict:
        user = AppUser.objects.filter(uid=self.uid).first()
        search_filters = SearchFilters(search=search)
        qs = get_filtered_published_runs(user, search_filters)

        results = [
            dict(
                title=pr.title,
                description=(pr.notes or "")[:300],
                workflow=Workflow(pr.workflow).label,
                run_url=pr.get_app_url(),
            )
            for pr in qs[:MAX_SEARCH_RESULTS]
        ]
        if not results:
            return dict(
                results=[],
                message=(
                    "No workflows found. This is a keyword search where every word "
                    "must match - retry with fewer, more generic keywords "
                    "(e.g. a single word like 'image')."
                ),
            )

        return dict(results=results)


NO_CURRENT_WORKFLOW_ERROR = (
    "No workflow is currently selected and no run_url was provided. "
    f"Call `{SearchWorkflowsLLMTool.name}` to find a workflow and pass its run_url to this tool."
)


class FetchWorkflowStateLLMTool(BaseLLMTool):
    disable_dynamic_loader = True

    name = "fetch_workflow_state"

    def __init__(self, page_cls: typing.Type[BasePage] | None):
        self.page_cls = page_cls
        super().__init__(
            name=self.name,
            label="Fetch Workflow State",
            description="Fetch the current state of a workflow",
            properties={"run_url": {"type": "string"}},
        )

    def call(self, run_url: str) -> typing.Any:
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

    page_cls: typing.Type[BasePage] | None
    sr: SavedRun | None
    pr: PublishedRun | None
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
        if not self.sr:
            raise ValueError(NO_CURRENT_WORKFLOW_ERROR)
        return self.page_cls, self.sr, self.pr

    def get_current_user(self) -> AppUser:
        return AppUser.objects.get(uid=self.builder_sr.uid)

    def get_current_workspace(self) -> Workspace:
        return self.builder_sr.workspace

    def should_create_new_runs(self, run_url: str | None, sr: SavedRun) -> bool:
        return bool(run_url or sr.parent_builder_saved_run_id != self.builder_sr.id)


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
        page_cls: typing.Type[BasePage] | None,
        sr: SavedRun | None,
        pr: PublishedRun | None,
        builder_sr: SavedRun,
    ):
        self.page_cls = page_cls
        self.sr = sr
        self.pr = pr
        self.builder_sr = builder_sr

        if sr:
            state = sr.state
            properties = page_cls.get_tool_call_schema(state)

            current_workflow_state = dict(
                request=extract_model_fields(page_cls.RequestModel, state),
                response=extract_model_fields(page_cls.ResponseModel, state),
            )
            description = (
                "Call this tool to update the current workflow state without running it.\n\n"
                f"Once updated you can run the updated workflow by calling the `{RunWorkflowLLMTool.name}` tool.\n"
                "By default, this tool will update the current workflow state. "
                f"You may call `{FetchWorkflowStateLLMTool.name}` to get the state of any workflow given its run_url "
                "and then call this tool with the run_url to update.\n\n"
                f"Current Workflow State: {json.dumps(jsonable_encoder(current_workflow_state))}"
            )
        else:
            properties = {}
            description = (
                "Call this tool to update a workflow's state without running it.\n\n"
                "There is no currently selected workflow, so you MUST pass `run_url`. "
                f"Call `{SearchWorkflowsLLMTool.name}` to find a workflow, then call "
                f"`{FetchWorkflowStateLLMTool.name}` with its run_url to get the "
                "workflow's state and schema properties before calling this tool.\n"
                f"Once updated you can run the updated workflow by calling the `{RunWorkflowLLMTool.name}` tool."
            )

        properties.update(
            {
                "run_url": run_url_prop("update", sr),
                "background": BACKGROUND_PROP,
            }
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
                surface=SavedRun.Surface.builder_child,
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
        page_cls: typing.Type[BasePage] | None,
        sr: SavedRun | None,
        pr: PublishedRun | None,
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
                "run_url": run_url_prop("run", sr),
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
                surface=SavedRun.Surface.builder_child,
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
        page_cls: typing.Type[BasePage] | None,
        sr: SavedRun | None,
        pr: PublishedRun | None,
        builder_sr: SavedRun,
    ):
        self.page_cls = page_cls
        self.sr = sr
        self.pr = pr
        self.builder_sr = builder_sr

        if pr:
            current_title = f"\n\nCurrent title: {pr.title}"
            current_description = f"\n\nCurrent description: {pr.notes}"
            last_change_notes = f"\n\nLast change notes: {sr.parent_version and sr.parent_version.change_notes}"
        else:
            current_title = ""
            current_description = ""
            last_change_notes = ""

        super().__init__(
            name=self.name,
            label="Save Workflow",
            description=(
                "Save changes to a published workflow as a new version. "
                "Call this when the user asks to save, publish, or update a workflow "
                "(including its title or description) in place. "
                "If the user wants to copy/duplicate/fork the workflow into a new one, "
                f"call `{SaveAsNewWorkflowLLMTool.name}` instead. "
                "Pass `run_url` to save a specific saved run "
                f"(e.g. the `run_url` returned by `{UpdateWorkflowStateLLMTool.name}`)."
            ),
            properties={
                "title": {
                    "type": "string",
                    "title": "Title",
                    "description": (
                        "Optional new value for the 'Title' "
                        "field in the Save Workflow dialog. "
                        "Leave unset to keep the existing title."
                        f"{current_title}"
                    ),
                },
                "description": {
                    "type": "string",
                    "title": "Description",
                    "description": (
                        "Optional new value for the 'Description' "
                        "field in the Save Workflow dialog "
                        "Leave unset to keep the existing description."
                        f"{current_description}"
                    ),
                },
                "change_notes": {
                    "type": "string",
                    "title": "Add change notes",
                    "description": "Used as the changelog entry for the new version."
                    f"{last_change_notes}",
                },
                "run_url": run_url_prop("save", sr),
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
        page_cls: typing.Type[BasePage] | None,
        sr: SavedRun | None,
        pr: PublishedRun | None,
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
                "Create a new published workflow that is a copy of an existing one. "
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
                "run_url": run_url_prop("save as new", sr),
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

        new_pr = page_cls.create_published_run(
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


def run_url_prop(action: str, sr: SavedRun | None) -> dict:
    if sr:
        description = (
            f"(optional) The url of the workflow to {action}. "
            "Defaults to the current workflow."
        )
    else:
        description = (
            f"The url of the workflow to {action}. "
            "Required because there is no currently selected workflow - "
            f"call `{SearchWorkflowsLLMTool.name}` to find one."
        )
    return {"type": "string", "description": description}
