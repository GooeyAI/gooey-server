# Generated by Django 4.2.5 on 2023-09-14 21:00
# ========= CUSTOM MIGRATION =========

from django.db import migrations, models


def migrate_info_to_conversation(apps, schema_editor):
    Conversation = apps.get_model("bots", "Conversation")
    BotIntegration = apps.get_model("bots", "BotIntegration")
    from bots.models import (
        Platform,
    )  # couldn't get this from the Apps registry so we'll have to assume Platform.SLACK isn't re-assigned in the future

    # for backwards compatibility, we might have to get the team id from the channel hook url
    for bi in BotIntegration.objects.filter(platform=Platform.SLACK):
        bi.slack_team_id = (
            bi.slack_team_id
            or bi.slack_channel_hook_url.removeprefix(
                "https://hooks.slack.com/services/"
            ).split("/")[0]
        )
        bi.save()

    for conv in Conversation.objects.all():
        bi = conv.bot_integration
        if bi.platform == Platform.SLACK:
            conv.slack_team_id = conv.slack_team_id or bi.slack_team_id
            conv.slack_channel_id = conv.slack_channel_id or bi.slack_channel_id
            conv.slack_channel_hook_url = (
                conv.slack_channel_hook_url or bi.slack_channel_hook_url
            )
            conv.save()


class Migration(migrations.Migration):
    dependencies = [
        ("bots", "0040_botintegration_slack_channel_name_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="slack_channel_hook_url",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Slack channel hook url, can be different than the bot integration's main channel (required if platform is Slack)",
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="slack_channel_id",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Slack channel id, can be different than the bot integration's main channel",
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="slack_team_id",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Slack team id, duplicate of bot integration value for indexing (required if platform is Slack)",
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="slack_use_threads",
            field=models.BooleanField(
                default=True,
                help_text="True if bot should reply in threads, otherwise it should post to the top level (required if platform is Slack)",
            ),
        ),
        migrations.RunPython(
            migrate_info_to_conversation,
            reverse_code=migrations.RunPython.noop,
            atomic=True,
        ),
        migrations.AddIndex(
            model_name="conversation",
            index=models.Index(
                fields=["slack_team_id", "slack_user_id", "slack_channel_id"],
                name="bots_conver_slack_t_fd21c2_idx",
            ),
        ),
    ]
