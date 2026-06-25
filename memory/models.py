from __future__ import annotations

from django.db import models

from functions.models import FunctionScopes


class MemoryEntry(models.Model):
    user_id = models.TextField()
    key = models.TextField()
    value = models.JSONField()

    saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.CASCADE,
        related_name="memory_entries",
        help_text="The last run that set this value",
    )

    scope = models.IntegerField(
        choices=FunctionScopes.db_choices(), null=True, blank=True, default=None
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        related_name="memory_entries",
        null=True,
        blank=True,
        default=None,
    )
    member = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.CASCADE,
        related_name="memory_entries",
        null=True,
        blank=True,
        default=None,
    )
    saved_workflow = models.ForeignKey(
        "bots.PublishedRun",
        on_delete=models.CASCADE,
        related_name="memory_entries",
        null=True,
        blank=True,
        default=None,
    )
    platform_user = models.TextField(default="", blank=True)
    deployment = models.ForeignKey(
        "bots.BotIntegration",
        on_delete=models.CASCADE,
        related_name="memory_entries",
        null=True,
        blank=True,
        default=None,
    )
    conversation = models.ForeignKey(
        "bots.Conversation",
        on_delete=models.CASCADE,
        related_name="memory_entries",
        null=True,
        blank=True,
        default=None,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user_id", "key")]
        verbose_name_plural = "Memory Entries"

    def __str__(self):
        return f"{self.user_id} - {self.key}"

    def write(self, key: str, value) -> tuple[MemoryEntry, bool]:
        return MemoryEntry.objects.update_or_create(
            user_id=self.user_id,
            key=key,
            defaults=dict(
                value=value,
                saved_run=self.saved_run,
                scope=self.scope,
                workspace=self.workspace,
                member=self.member,
                saved_workflow=self.saved_workflow,
                platform_user=self.platform_user,
                deployment=self.deployment,
                conversation=self.conversation,
            ),
        )
