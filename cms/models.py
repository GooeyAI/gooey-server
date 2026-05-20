from django.db import models

from bots.custom_fields import CustomURLField


class WorkflowTab(models.Model):
    title = models.CharField(max_length=64)
    icon = models.TextField(blank=True, default="")
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Workflow Tab"
        verbose_name_plural = "Workflow Tabs"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class WorkflowCard(models.Model):
    workflow_tab = models.ForeignKey(
        WorkflowTab,
        on_delete=models.CASCADE,
        related_name="cards",
    )
    recipe = models.ForeignKey(
        "bots.PublishedRun",
        on_delete=models.PROTECT,
        related_name="+",
    )
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.workflow_tab.title} — {self.recipe}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class IndustryTile(models.Model):
    tag = models.ForeignKey(
        "bots.Tag",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Workflows tagged with this Tag are counted on the tile.",
    )
    order = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.tag.name if self.tag_id else "Industry Tile"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class NewsItem(models.Model):
    headline = models.CharField(max_length=200)
    tag = models.CharField(
        max_length=64,
        help_text='Freeform label, e.g. "Event", "Product", "Case Study".',
    )
    photo_url=CustomURLField(default="", blank=True)
    publish_date = models.DateField()
    url = models.CharField(
        max_length=500, help_text="Absolute URL the card links to."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-publish_date", "-id"]
        indexes = [models.Index(fields=["-publish_date"])]

    def __str__(self):
        return self.headline
