from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workspaces", "0014_workspace_public_by_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="workspace",
            name="gmail_user_email",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Connected Gmail address",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="workspace",
            name="gmail_access_token",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Gmail OAuth2 access token",
            ),
        ),
        migrations.AddField(
            model_name="workspace",
            name="gmail_refresh_token",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Gmail OAuth2 refresh token",
            ),
        ),
        migrations.AddField(
            model_name="workspace",
            name="gmail_history_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Last processed Gmail historyId for incremental sync",
                max_length=50,
            ),
        ),
    ]
