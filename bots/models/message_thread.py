from django.db import models
from django.contrib import admin


class MessageThread(models.Model):
    """
    A message thread is a collection of runs that are related to a single conversation.
    It may not necessarily contain all the runs that are related to a conversation,
    only aims to identify a unique branch of the run tree for grouping purposes.
    """

    title = models.TextField(blank=True)

    bot_conversation = models.OneToOneField(
        "bots.Conversation",
        on_delete=models.CASCADE,
        related_name="message_thread",
        null=True,
        blank=True,
        default=None,
    )

    first_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.SET_NULL,
        related_name="threads_as_first_run",
        null=True,
        blank=True,
        default=None,
    )

    last_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.SET_NULL,
        related_name="threads_as_last_run",
        null=True,
        blank=True,
        default=None,
    )

    def __str__(self):
        return self.title

    @admin.display(description="Created at", ordering="first_run__created_at")
    def get_created_at(self):
        return self.first_run and self.first_run.created_at

    @admin.display(description="Updated at", ordering="last_run__updated_at")
    def get_updated_at(self):
        return self.last_run and self.last_run.updated_at
