from django.db import models


class MemoryEntry(models.Model):
    user_id = models.TextField()
    key = models.TextField()
    value = models.JSONField()

    saved_run = models.ForeignKey(
        "bots.SavedRun", on_delete=models.CASCADE, related_name="memory_values"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user_id", "key")]
        verbose_name_plural = "Memory Entries"

    def __str__(self):
        return f"{self.user_id} - {self.key}"
