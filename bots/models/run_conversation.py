from django.contrib import admin
from django.db import models


class RunConversation(models.Model):
    first_msg = models.ForeignKey(
        "bots.SavedRun",
        related_name="starting_conversations",
        on_delete=models.CASCADE,
        help_text="First run of this conversation.",
    )

    last_msg = models.OneToOneField(
        "bots.SavedRun",
        related_name="run_conversation",
        on_delete=models.CASCADE,
        help_text="Current latest turn of this conversation.",
    )

    messages = models.ManyToManyField(
        "bots.SavedRun",
        help_text="Runs that make up the turns of this conversation.",
    )

    title = models.TextField(blank=True)

    bot_conversation = models.OneToOneField(
        "bots.Conversation",
        on_delete=models.CASCADE,
        related_name="run_conversation",
        null=True,
        blank=True,
        default=None,
    )

    def __str__(self):
        return self.title

    @admin.display(description="Created at", ordering="first_msg__created_at")
    def get_created_at(self):
        return self.first_msg.created_at

    @admin.display(description="Updated at", ordering="last_msg__updated_at")
    def get_updated_at(self):
        return self.last_msg.updated_at
