from __future__ import annotations

from django.db import models, transaction

from bots.models.saved_run import SavedRun


class RunConversationQuerySet(models.QuerySet):
    def for_listing(
        self,
        *,
        workspace,
        surface: int,
        workflow: int | None = None,
        uid: str | None = None,
    ):
        """Conversations for a workspace, newest activity first.

        workflow=None lists across all workflows (e.g. the builder sidebar, which
        spans every workflow it can build); uid filters to one owner.
        """
        qs = self.filter(workspace=workspace, surface=surface)
        if workflow is not None:
            qs = qs.filter(workflow=workflow)
        if uid is not None:
            qs = qs.filter(uid=uid)
        return qs


class RunConversation(models.Model):
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        related_name="run_conversations",
    )
    uid = models.CharField(max_length=255, db_index=True)
    workflow = models.IntegerField()
    surface = models.IntegerField(choices=SavedRun.Surface.choices)

    title = models.TextField(blank=True, default="")
    last_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
        default=None,
        help_text="The latest turn of this conversation (resume target + list preview).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = RunConversationQuerySet.as_manager()

    class Meta:
        # Every listing query filters (workspace, surface) and sorts by
        # -updated_at; workflow/uid are optional residual filters. workspace is
        # always present and far more selective than workflow, so a single
        # workspace-leading index covers the builder sidebar, chat widget, and
        # history tab. surface precedes uid so (workspace, surface) stays a clean
        # prefix for the no-uid queries.
        indexes = [
            models.Index(fields=["workspace", "surface", "uid", "-updated_at"]),
        ]

    def __str__(self):
        return f"{self.get_surface_display()} conversation: {self.title[:40]!r}"

    @classmethod
    def attach_run(
        cls,
        *,
        sr: SavedRun,
        parent_sr: SavedRun | None,
        is_continuation: bool,
        surface: int,
        title: str,
    ) -> RunConversation:
        """Link `sr` to its conversation: continue the parent's thread, or start a new one.

        Also moves the conversation head (`last_run`) to `sr` and bumps `updated_at`.
        """
        title = (title or "").strip()

        convo = None
        if is_continuation and parent_sr is not None and parent_sr.conversation_id:
            parent_convo = parent_sr.conversation
            if parent_convo.accepts_turn(sr, surface):
                convo = parent_convo

        with transaction.atomic():
            if convo is None:
                convo = cls.objects.create(
                    workspace_id=sr.workspace_id,
                    uid=sr.uid or "",
                    workflow=sr.workflow,
                    surface=surface,
                    title=title,
                )

            sr.conversation = convo
            sr.save(update_fields=["conversation"])

            convo.last_run = sr
            if not convo.title:
                convo.title = title
            convo.save(update_fields=["last_run", "title", "updated_at"])
        return convo

    def accepts_turn(self, sr: SavedRun, surface: int) -> bool:
        """Whether a turn (`sr`, produced on `surface`) belongs to this thread.

        A continuation may join its parent's conversation only when every scope
        boundary lines up. SavedRun.parent carries no workspace/uid constraint,
        so without this check a turn could attach to a conversation owned by a
        different workspace, user, surface, or workflow -- mis-grouping turns
        and leaking threads across users in shared workspaces.
        """
        return (
            self.workspace_id == sr.workspace_id
            and (self.uid or "") == (sr.uid or "")
            and self.workflow == sr.workflow
            and self.surface == surface
        )
