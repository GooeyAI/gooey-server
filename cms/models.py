from django.db import models
from django.utils import timezone

from bots.custom_fields import CustomURLField


class WorkflowTab(models.Model):
    workflow_metadata = models.ForeignKey(
        "bots.WorkflowMetadata",
        on_delete=models.PROTECT,
        related_name="workflow_tabs",
        verbose_name="Workflow type",
    )
    priority = models.IntegerField(
        default=1,
        help_text="Higher priority tabs are shown first. If 0, then the tab is not shown at all.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-priority", "id"]
        verbose_name = "Workflow Tab"
        verbose_name_plural = "Workflow Tabs"

    def __str__(self):
        return self.workflow_metadata.short_title


class WorkflowCard(models.Model):
    workflow_tab = models.ForeignKey(
        WorkflowTab,
        on_delete=models.CASCADE,
        related_name="cards",
    )
    workflow = models.ForeignKey(
        "bots.PublishedRun",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Workflow",
    )
    priority = models.IntegerField(
        default=1,
        help_text="Higher priority cards are shown first. If 0, then the card is not shown at all.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-priority", "id"]

    def __str__(self):
        return f"{self.workflow_tab} — {self.workflow}"


class NewsItem(models.Model):
    headline = models.CharField(max_length=200)
    tag = models.CharField(
        max_length=64,
        help_text='Freeform label, e.g. "Event", "Product", "Case Study".',
    )
    photo_url = CustomURLField(default="", blank=True)
    publish_date = models.DateTimeField(default=timezone.now)
    url = CustomURLField(default="", blank=False, help_text="News item URL.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.headline
