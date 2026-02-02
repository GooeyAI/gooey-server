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
from functions.models import CalledFunctionResponse
from gooeysite.bg_db_conn import get_celery_result_db_safe
from . import Platform
from .workflow import Workflow

if typing.TYPE_CHECKING:
    import celery.result
    import pandas as pd

    from .published_run import PublishedRun


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
    run_id = models.CharField(max_length=128, default=None, null=True, blank=True)
    uid = models.CharField(max_length=128, default=None, null=True, blank=True)
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

    is_api_call = models.BooleanField(default=False)

    platform = models.IntegerField(
        choices=Platform.choices, null=True, blank=True, default=None
    )
    user_message_id = models.TextField(null=True, blank=True, default=None)

    objects = SavedRunQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        unique_together = [
            ["workflow", "example_id"],
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
            models.Index(fields=["workflow", "example_id", "run_id", "uid"]),
            models.Index(fields=["workflow", "example_id", "hidden"]),
            models.Index(fields=["workflow", "uid", "updated_at", "workspace"]),
        ]

    def __str__(self):
        from daras_ai_v2.breadcrumbs import get_title_breadcrumbs

        title = get_title_breadcrumbs(
            Workflow(self.workflow).page_cls, self, self.parent_published_run()
        ).title_with_prefix()
        return title or self.get_app_url()

    def parent_published_run(self) -> PublishedRun | None:
        return self.parent_version and self.parent_version.published_run

    def get_app_url(self, query_params: dict = None):
        return Workflow(self.workflow).page_cls.app_url(
            example_id=self.example_id,
            run_id=self.run_id,
            uid=self.uid,
            query_params=query_params,
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
        if not state:
            return

        self.copy_from_firebase_state(state)
        self.save()

    def copy_from_firebase_state(self, state: dict) -> "SavedRun":
        from daras_ai_v2.base import StateKeys

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

        return self

    def submit_api_call(
        self,
        *,
        workspace: "Workspace",
        request_body: dict,
        enable_rate_limits: bool = False,
        deduct_credits: bool = True,
        parent_pr: PublishedRun | None = None,
        current_user: AppUser | None = None,
    ) -> tuple["celery.result.AsyncResult", "SavedRun"]:
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
                ),
            )

    def wait_for_celery_result(self, result: "celery.result.AsyncResult"):
        get_celery_result_db_safe(result)
        self.refresh_from_db()

    def get_creator(self) -> AppUser | None:
        if self.uid:
            return AppUser.objects.filter(uid=self.uid).first()
        else:
            return None

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


def _parse_dt(dt) -> datetime.datetime | None:
    if isinstance(dt, str):
        return datetime.datetime.fromisoformat(dt)
    elif isinstance(dt, datetime.datetime):
        return datetime.datetime.fromtimestamp(dt.timestamp(), dt.tzinfo)
    return None
