from __future__ import annotations

from django.db import models

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
        indexes = [
            models.Index(fields=["workflow", "workspace", "surface", "-updated_at"]),
            models.Index(fields=["workflow", "uid", "surface", "-updated_at"]),
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
        if is_continuation and parent_sr is not None and parent_sr.conversation_id:
            convo = parent_sr.conversation
        else:
            convo = cls.objects.create(
                workspace_id=sr.workspace_id,
                uid=sr.uid,
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
