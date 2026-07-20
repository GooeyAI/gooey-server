from __future__ import annotations

import datetime
import typing
from multiprocessing.pool import ThreadPool

import pytz
from django.conf import settings
from django.contrib import admin
from django.db import models
from django.db.models import IntegerChoices

from app_users.models import AppUser
from bots.admin_links import open_in_new_tab
from bots.custom_fields import PostgresJSONEncoder
from daras_ai_v2.crypto import get_random_doc_id
from functions.models import CalledFunctionResponse
from gooeysite.bg_db_conn import get_celery_result_db_safe
from . import Platform
from .workflow import Workflow, WorkflowMetadata

if typing.TYPE_CHECKING:
    import celery.result
    import pandas as pd

    from functions.models import CalledFunction
    from .published_run import PublishedRun, PublishedRunVersion
    from workspaces.models import Workspace


class SavedRunQuerySet(models.QuerySet):
    def to_df(self, tz=pytz.timezone(settings.TIME_ZONE)) -> "pd.DataFrame":
        import pandas as pd

        # export only the first 10,000 records
        qs = self.all()[:10_000]
        # Convert the queryset to a list of dicts
        records = [sr.to_dict() | {"web_url": sr.get_app_url()} for sr in qs]
        # Convert the list of dicts to a dataframe
        df = pd.DataFrame.from_records(records)
        # Identify datetime columns and convert them to the specified timezone
        for column, dtype in df.dtypes.items():
            if not pd.api.types.is_datetime64_any_dtype(dtype):
                continue
            df[column] = df[column].dt.tz_convert(tz)
        return df


class RetentionPolicy(IntegerChoices):
    keep = 0, "Keep"
    delete = 1, "Delete"


class SavedRun(models.Model):
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="Parent Run",
    )
    parent_version = models.ForeignKey(
        "bots.PublishedRunVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children_runs",
    )

    workflow = models.IntegerField(
        choices=Workflow.choices, default=Workflow.VIDEO_BOTS
    )
    workflow_metadata = models.ForeignObject(
        "bots.WorkflowMetadata",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        from_fields=["workflow"],
        to_fields=["workflow"],
        related_name="saved_runs",
    )
    run_id = models.CharField(max_length=128, default=None, null=True, blank=True)
    uid = models.CharField(max_length=128, default=None, null=True, blank=True)
    created_by = models.ForeignObject(
        "app_users.AppUser",
        null=True,
        blank=True,
        on_delete=models.DO_NOTHING,
        from_fields=["uid"],
        to_fields=["uid"],
        related_name="saved_runs",
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.SET_NULL,
        related_name="saved_runs",
        null=True,
    )

    state = models.JSONField(default=dict, blank=True, encoder=PostgresJSONEncoder)

    error_msg = models.TextField(
        default="",
        blank=True,
        help_text="The error message. If this is not set, the run is deemed successful.",
    )
    run_time = models.DurationField(default=datetime.timedelta, blank=True)
    run_status = models.TextField(default="", blank=True)

    error_code = models.IntegerField(
        null=True,
        default=None,
        blank=True,
        help_text="The HTTP status code of the error. If this is not set, 500 is assumed.",
    )
    error_type = models.TextField(
        default="", blank=True, help_text="The exception type"
    )
    error_params = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured error parameters for UI rendering or API responses.",
    )

    hidden = models.BooleanField(default=False)
    is_flagged = models.BooleanField(default=False)

    price = models.IntegerField(default=0)
    transaction = models.ForeignKey(
        "app_users.AppUserTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="saved_runs",
    )

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    example_id = models.CharField(
        max_length=128, default=None, null=True, blank=True, help_text="(Deprecated)"
    )
    page_title = models.TextField(default="", blank=True, help_text="(Deprecated)")
    page_notes = models.TextField(default="", blank=True, help_text="(Deprecated)")

    retention_policy = models.IntegerField(
        choices=RetentionPolicy.choices, default=RetentionPolicy.keep
    )

    class Surface(IntegerChoices):
        run = 0, "Run"
        api = 1, "API"
        deployment = 2, "Deployment"
        builder_prompt = 3, "Builder Prompt"
        builder_child = 4, "Builder"
        tool_call = 5, "Tool Call"
        internal = 6, "Internal"
        analysis = 7, "Analysis"
        export = 8, "Export"
        bulk = 9, "Bulk"

    surface = models.IntegerField(
        choices=Surface.choices,
        default=Surface.run,
        help_text="Where this run was created.<br><br>"
        f"{Surface.run.label}: A run created from the UI playground directly by the user.<br>"
        f"{Surface.api.label}: Called by an API.<br>"
        f"{Surface.deployment.label}: Called by a bot integration.<br>"
        f"{Surface.builder_prompt.label}: A prompt submitted to the Gooey builder.<br>"
        f"{Surface.builder_child.label}: A child run created by the Gooey builder.<br>"
        f"{Surface.tool_call.label}: Any tool calls made by a workflow.<br>"
        f"{Surface.internal.label}: Any internal calls made by the app, e.g. QR code or icon generator.<br>"
        f"{Surface.analysis.label}: A run created from the bot integration analysis feature.<br>"
        f"{Surface.export.label}: A run created from the scheduled bot integration export feature.<br>"
        f"{Surface.bulk.label}: A run created from the bulk runner.",
    )
    is_api_call = models.BooleanField(
        default=False,
        help_text="(Deprecated) Use surface instead.",
    )

    # see signals.py:revoke_saved_run_task_on_cancel
    is_cancelled = models.BooleanField(default=False)
    celery_task_id = models.CharField(
        max_length=255,
        default="",
        blank=True,
        help_text="ID of the Celery task currently executing this run, used to revoke it on cancel.",
    )

    platform = models.IntegerField(
        choices=Platform.choices, null=True, blank=True, default=None
    )
    user_message_id = models.TextField(null=True, blank=True, default=None)

    parent_builder_saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.SET_NULL,
        related_name="child_builder_saved_runs",
        null=True,
        blank=True,
        default=None,
        help_text="The Parent Gooey Builder SavedRun that created this run",
    )
    redirect_url = models.TextField(
        blank=True,
        default="",
        help_text="The URL to redirect the user to after the builder run is complete",
    )

    message_thread = models.ForeignKey(
        "bots.MessageThread",
        on_delete=models.CASCADE,
        related_name="saved_runs",
        null=True,
        blank=True,
        default=None,
    )

    objects = SavedRunQuerySet.as_manager()

    class Meta:
        unique_together = [
            ["run_id", "uid"],
            ["platform", "user_message_id"],
        ]
        constraints = [
            models.CheckConstraint(
                # ensure that the parent is not the same as the current record
                check=~models.Q(parent=models.F("id")),
                name="parent_not_self",
            ),
        ]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["-updated_at"]),
            models.Index(fields=["workflow"]),
            models.Index(fields=["uid"]),
            models.Index(fields=["run_id", "uid"]),
            models.Index(fields=["workflow", "run_id", "uid"]),
            models.Index(fields=["workflow", "uid", "-updated_at"]),
            models.Index(fields=["workflow", "workspace", "-updated_at"]),
            models.Index(fields=["workflow", "uid", "workspace", "-updated_at"]),
            # used by gooey_builder.py:fetch_builder_conversations
            models.Index(fields=["uid", "workspace", "surface", "-updated_at"]),
            # used by widgets/history.py for workspace-level history listing
            models.Index(fields=["workspace", "surface", "-updated_at"]),
        ]

    def __str__(self):
        from daras_ai_v2.breadcrumbs import get_title_breadcrumbs

        title = get_title_breadcrumbs(
            Workflow(self.workflow).page_cls, self, self.parent_published_run()
        ).title_with_prefix()
        return title or self.get_app_url()

    def get_workflow_metadata(self) -> WorkflowMetadata:
        try:
            metadata = self.workflow_metadata
        except WorkflowMetadata.DoesNotExist:
            metadata = None
        return metadata or Workflow(self.workflow).get_or_create_metadata()

    def parent_published_run(self) -> PublishedRun | None:
        return self.parent_version and self.parent_version.published_run

    def get_app_url(self, query_params: dict | None = None):
        query_params = query_params or {}
        return Workflow(self.workflow).page_cls.raw_app_url(
            query_params=query_params | dict(run_id=self.run_id, uid=self.uid),
        )

    def to_dict(self) -> dict:
        from daras_ai_v2.base import StateKeys

        ret = self.state.copy()
        if self.updated_at:
            ret[StateKeys.updated_at] = self.updated_at
        if self.created_at:
            ret[StateKeys.created_at] = self.created_at
        if self.error_msg:
            ret[StateKeys.error_msg] = self.error_msg
        if self.run_time:
            ret[StateKeys.run_time] = self.run_time.total_seconds()
        if self.run_status:
            ret[StateKeys.run_status] = self.run_status
        if self.hidden:
            ret[StateKeys.hidden] = self.hidden
        if self.is_flagged:
            ret["is_flagged"] = self.is_flagged
        if self.price:
            ret["price"] = self.price
        return ret

    def set(self, state: dict):
        from daras_ai_v2.base import StateKeys

        if not state:
            return
        state = state.copy()
        # ignore updated_at from firebase, we use auto_now=True
        state.pop(StateKeys.updated_at, None)
        # self.updated_at = _parse_dt() or EPOCH
        created_at = _parse_dt(state.pop(StateKeys.created_at, None))
        if created_at:
            self.created_at = created_at
        self.error_msg = state.pop(StateKeys.error_msg, None) or ""
        self.run_time = datetime.timedelta(
            seconds=state.pop(StateKeys.run_time, None) or 0
        )
        self.run_status = state.pop(StateKeys.run_status, None) or ""
        self.is_flagged = state.pop("is_flagged", False)
        self.state = state

        self.save(
            update_fields=[
                "created_at",
                "updated_at",
                "error_msg",
                "run_time",
                "run_status",
                "is_flagged",
                "state",
            ]
        )

    def submit_api_call(
        self,
        *,
        current_user: AppUser,
        workspace: Workspace,
        request_body: dict,
        enable_rate_limits: bool = False,
        deduct_credits: bool = True,
        parent_pr: PublishedRun | None = None,
        called_fn: CalledFunction | None = None,
        **defaults,
    ) -> tuple[celery.result.AsyncResult, SavedRun]:
        from routers.api import submit_api_call

        # run in a thread to avoid messing up threadlocals
        with ThreadPool(1) as pool:
            page_cls = Workflow(self.workflow).page_cls
            if parent_pr and parent_pr.saved_run == self:
                # avoid passing run_id and uid for examples
                query_params = dict(example_id=parent_pr.published_run_id)
            else:
                query_params = page_cls.clean_query_params(
                    example_id=self.example_id, run_id=self.run_id, uid=self.uid
                )
            return pool.apply(
                submit_api_call,
                kwds=dict(
                    page_cls=page_cls,
                    query_params=query_params,
                    workspace=workspace,
                    current_user=current_user,
                    request_body=request_body,
                    enable_rate_limits=enable_rate_limits,
                    deduct_credits=deduct_credits,
                    called_fn=called_fn,
                    **defaults,
                ),
            )

    def wait_for_celery_result(self, result: celery.result.AsyncResult):
        get_celery_result_db_safe(result)
        self.refresh_from_db()

    @admin.display(description="Open in Gooey")
    def open_in_gooey(self):
        return open_in_new_tab(self.get_app_url(), label=self.get_app_url())

    def api_output(self, state: dict = None) -> dict:
        state = state or self.state
        if self.state.get("functions"):
            state["called_functions"] = [
                CalledFunctionResponse.from_db(called_fn)
                for called_fn in self.called_functions.all()
            ]
        return state

    def clone(
        self,
        *,
        parent_pr: PublishedRun | None = None,
        uid: str | None = None,
        workspace_id: int | None = None,
        **kwargs,
    ) -> SavedRun:
        parent_version_id = self.parent_version_id
        if parent_pr:
            try:
                parent_version_id = parent_pr.versions.latest("id").id
            except PublishedRunVersion.DoesNotExist:
                pass
        if uid is None:
            uid = self.uid
        if workspace_id is None:
            workspace_id = self.workspace_id
        return SavedRun(
            parent_id=self.id,
            parent_version_id=parent_version_id,
            workflow=self.workflow,
            run_id=get_random_doc_id(),
            uid=uid,
            workspace_id=workspace_id,
            state=self.state,
            error_msg=self.error_msg,
            run_time=self.run_time,
            error_code=self.error_code,
            error_type=self.error_type,
            error_params=self.error_params,
            price=self.price,
            **kwargs,
        )


def _parse_dt(dt) -> datetime.datetime | None:
    if isinstance(dt, str):
        return datetime.datetime.fromisoformat(dt)
    elif isinstance(dt, datetime.datetime):
        return datetime.datetime.fromtimestamp(dt.timestamp(), dt.tzinfo)
    return None
