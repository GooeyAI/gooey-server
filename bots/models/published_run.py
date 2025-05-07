from __future__ import annotations

import typing

from django.contrib import admin
from django.db import models, transaction
from django.db.models import Q

from app_users.models import AppUser
from bots.admin_links import open_in_new_tab
from bots.custom_fields import CustomURLField
from daras_ai_v2.crypto import get_random_doc_id
from gooeysite.custom_create import get_or_create_lazy
from workspaces.models import Workspace

from .saved_run import SavedRun
from .workflow import Workflow, WorkflowAccessLevel

if typing.TYPE_CHECKING:
    import celery.result


class PublishedRunQuerySet(models.QuerySet):
    def get_or_create_with_version(
        self,
        *,
        workflow: Workflow,
        published_run_id: str,
        saved_run: SavedRun,
        user: AppUser | None,
        workspace: typing.Optional["Workspace"],
        title: str,
        notes: str = "",
        public_access: WorkflowAccessLevel | None = None,
        photo_url: str = "",
    ):
        return get_or_create_lazy(
            PublishedRun,
            workflow=workflow,
            published_run_id=published_run_id,
            create=lambda **kwargs: self.create_with_version(
                **kwargs,
                saved_run=saved_run,
                user=user,
                workspace=workspace,
                title=title,
                notes=notes,
                public_access=public_access,
                photo_url=photo_url,
            ),
        )

    def create_with_version(
        self,
        *,
        workflow: Workflow,
        published_run_id: str,
        saved_run: SavedRun,
        user: AppUser | None,
        workspace: typing.Optional["Workspace"],
        title: str,
        notes: str,
        public_access: WorkflowAccessLevel | None = None,
        photo_url: str = "",
    ):
        workspace_id = (
            workspace
            and workspace.id
            or PublishedRun._meta.get_field("workspace").get_default()
        )
        if not public_access:
            if workspace and workspace.can_have_private_published_runs():
                public_access = WorkflowAccessLevel.VIEW_ONLY
            else:
                public_access = WorkflowAccessLevel.FIND_AND_VIEW

        with transaction.atomic():
            pr = self.create(
                workflow=workflow,
                published_run_id=published_run_id,
                created_by=user,
                last_edited_by=user,
                workspace_id=workspace_id,
                title=title,
                photo_url=photo_url,
            )
            pr.add_version(
                user=user,
                saved_run=saved_run,
                title=title,
                public_access=public_access,
                notes=notes,
                photo_url=photo_url,
            )
            return pr


def get_default_published_run_workspace():
    from workspaces.models import Workspace

    created_by, _ = AppUser.objects.filter(
        email__endswith="dara.network",
    )[:1].get_or_create(
        defaults=dict(
            email="support@dara.network", is_anonymous=False, balance=0, uid="<_blank>"
        ),
    )
    return Workspace.objects.get_or_create(
        domain_name="dara.network",
        defaults=dict(
            name="Gooey.AI (Dara.network Inc)",
            created_by=created_by,
            is_paying=True,
        ),
    )[0].id


class PublishedRun(models.Model):
    # published_run_id was earlier SavedRun.example_id
    published_run_id = models.CharField(
        max_length=128,
        blank=True,
    )

    saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.PROTECT,
        related_name="published_runs",
        null=True,
    )
    workflow = models.IntegerField(
        choices=Workflow.choices,
    )
    title = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    public_access = models.IntegerField(
        choices=WorkflowAccessLevel.choices,
        default=WorkflowAccessLevel.FIND_AND_VIEW,
    )
    workspace_access = models.IntegerField(
        choices=WorkflowAccessLevel.choices,
        default=WorkflowAccessLevel.EDIT,
    )
    is_approved_example = models.BooleanField(default=False)
    example_priority = models.IntegerField(
        default=1,
        help_text="Priority of the example in the example list",
    )

    run_count = models.IntegerField(default=0)

    created_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="published_runs",
        blank=True,
    )
    last_edited_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        default=get_default_published_run_workspace,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PublishedRunQuerySet.as_manager()
    photo_url = CustomURLField(default="", blank=True)

    class Meta:
        get_latest_by = "updated_at"

        ordering = ["-updated_at"]
        unique_together = [
            ["workflow", "published_run_id"],
        ]

        indexes = [
            models.Index(fields=["workflow", "created_by"]),
            models.Index(fields=["workflow", "published_run_id"]),
            models.Index(
                fields=[
                    "is_approved_example",
                    "public_access",
                    "workspace_access",
                    "published_run_id",
                    "updated_at",
                    "workflow",
                    "example_priority",
                ]
            ),
            models.Index(
                fields=[
                    "-updated_at",
                    "workspace",
                    "created_by",
                    "public_access",
                    "workspace_access",
                ]
            ),
            models.Index(fields=["published_run_id"]),
            # GinIndex(
            #     SearchVector("title", "notes", config="english"),
            #     name="publishedrun_search_vector_idx",
            # ),
        ]

    def __str__(self):
        return self.title or self.get_app_url()

    @admin.display(description="Open in Gooey")
    def open_in_gooey(self):
        return open_in_new_tab(self.get_app_url(), label=self.get_app_url())

    def duplicate(
        self,
        *,
        user: AppUser,
        workspace: "Workspace",
        title: str,
        notes: str,
        public_access: WorkflowAccessLevel | None = None,
    ) -> "PublishedRun":
        return PublishedRun.objects.create_with_version(
            workflow=Workflow(self.workflow),
            published_run_id=get_random_doc_id(),
            saved_run=self.saved_run,
            user=user,
            workspace=workspace,
            title=title,
            notes=notes,
            public_access=public_access,
        )

    def get_app_url(self, query_params: dict = None):
        return Workflow(self.workflow).page_cls.app_url(
            example_id=self.published_run_id, query_params=query_params
        )

    def add_version(
        self,
        *,
        user: AppUser | None,
        saved_run: SavedRun,
        public_access: WorkflowAccessLevel | None = None,
        workspace_access: WorkflowAccessLevel | None = None,
        title: str = "",
        notes: str = "",
        change_notes: str = "",
        photo_url: str = "",
    ):
        assert saved_run.workflow == self.workflow

        if public_access is None:
            public_access = self.public_access
        if workspace_access is None:
            workspace_access = self.workspace_access
        with transaction.atomic():
            version = PublishedRunVersion(
                published_run=self,
                version_id=get_random_doc_id(),
                saved_run=saved_run,
                changed_by=user,
                title=title,
                notes=notes,
                public_access=public_access,
                workspace_access=workspace_access,
                change_notes=change_notes,
                photo_url=photo_url,
            )
            version.save()
            self.update_fields_to_latest_version()

    def is_root(self):
        return not self.published_run_id

    def update_fields_to_latest_version(self):
        latest_version = self.versions.latest()
        self.saved_run = latest_version.saved_run
        self.last_edited_by = latest_version.changed_by
        self.title = latest_version.title
        self.notes = latest_version.notes
        self.public_access = latest_version.public_access
        self.workspace_access = latest_version.workspace_access
        self.photo_url = latest_version.photo_url

        self.save()

    def get_share_icon(self):
        """
        Shown internally to workspace members. For example: share button on workflow page.
        """
        if self.workspace.is_personal:
            return WorkflowAccessLevel(self.public_access).get_public_sharing_icon()
        else:
            return WorkflowAccessLevel(self.workspace_access).get_team_sharing_icon()

    def get_share_badge_html(self):
        """
        Shown externally AND on listings. For example: saved list, profile page.
        """
        if self.workspace.is_personal or (
            self.public_access == WorkflowAccessLevel.FIND_AND_VIEW
        ):
            perm = WorkflowAccessLevel(self.public_access)
            return f"{perm.get_public_sharing_icon()} {perm.get_public_sharing_label()}"

        perm = WorkflowAccessLevel(self.workspace_access)
        if self.workspace_access == WorkflowAccessLevel.VIEW_ONLY:
            return f"{perm.get_team_sharing_icon()} {perm.get_team_sharing_label()}"
        else:
            return f"{self.workspace.html_icon(size='20px')} {perm.get_team_sharing_label()}"

    def submit_api_call(
        self,
        *,
        workspace: "Workspace",
        request_body: dict,
        enable_rate_limits: bool = False,
        deduct_credits: bool = True,
        current_user: AppUser | None = None,
    ) -> tuple[celery.result.AsyncResult, SavedRun]:
        return self.saved_run.submit_api_call(
            workspace=workspace,
            current_user=current_user,
            request_body=request_body,
            enable_rate_limits=enable_rate_limits,
            deduct_credits=deduct_credits,
            parent_pr=self,
        )

    @classmethod
    def approved_example_q(cls):
        return (
            Q(is_approved_example=True)
            & ~Q(public_access=WorkflowAccessLevel.VIEW_ONLY.value)
            & ~Q(published_run_id="")
        )


class PublishedRunVersion(models.Model):
    version_id = models.CharField(max_length=128, unique=True)

    published_run = models.ForeignKey(
        PublishedRun,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.PROTECT,
        related_name="published_run_versions",
    )
    changed_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    title = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    change_notes = models.TextField(blank=True, default="")
    public_access = models.IntegerField(
        choices=WorkflowAccessLevel.choices,
        default=WorkflowAccessLevel.VIEW_ONLY,
    )
    workspace_access = models.IntegerField(
        choices=WorkflowAccessLevel.choices,
        default=WorkflowAccessLevel.EDIT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    photo_url = CustomURLField(default="", blank=True)

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = "created_at"
        indexes = [
            models.Index(fields=["published_run", "-created_at"]),
            models.Index(fields=["version_id"]),
            models.Index(fields=["changed_by"]),
        ]

    def __str__(self):
        return f"{self.published_run} - {self.version_id}"
