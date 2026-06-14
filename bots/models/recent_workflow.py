from django.db import models


class WorkspaceRecentWorkflow(models.Model):
    """
    Denormalized "last used" index of published runs per workspace (and user).

    One row per (workspace, uid, published_run), upserted whenever a run is
    created from a published run. Lets the home page read a workspace's recent
    workflows in O(distinct workflows) instead of scanning the entire SavedRun
    history for that workspace.
    """

    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        related_name="recent_workflows",
    )
    uid = models.CharField(max_length=128, null=True, blank=True, default=None)
    published_run = models.ForeignKey(
        "bots.PublishedRun",
        on_delete=models.CASCADE,
        related_name="recent_usages",
    )
    # the user's latest run of this workflow, used to render the card directly
    last_saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.CASCADE,
        related_name="+",
    )
    last_used_at = models.DateTimeField()

    class Meta:
        unique_together = [["workspace", "uid", "published_run"]]
        indexes = [
            models.Index(fields=["workspace", "uid", "-last_used_at"]),
        ]

    def __str__(self):
        return f"{self.published_run_id} in {self.workspace_id} @ {self.last_used_at:%Y-%m-%d %H:%M}"
