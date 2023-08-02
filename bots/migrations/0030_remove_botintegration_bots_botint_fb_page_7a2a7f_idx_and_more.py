# Generated by Django 4.2.3 on 2023-08-02 02:46

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bots", "0029_alter_savedrun_updated_at"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="botintegration",
            name="bots_botint_fb_page_7a2a7f_idx",
        ),
        migrations.AddField(
            model_name="botintegration",
            name="slack_access_token",
            field=models.TextField(
                blank=True,
                default="",
                editable=False,
                help_text="Bot's Slack access token (required if platform is Slack)",
            ),
        ),
        migrations.AddField(
            model_name="botintegration",
            name="slack_channel_hook_url",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Bot's Slack channel hook url (required if platform is Slack)",
            ),
        ),
        migrations.AddField(
            model_name="botintegration",
            name="slack_channel_id",
            field=models.CharField(
                blank=True,
                default=None,
                help_text="Bot's Slack channel id (required if platform is Slack)",
                max_length=256,
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="slack_user_id",
            field=models.TextField(
                blank=True,
                db_index=True,
                default="",
                help_text="User's Slack channel id (required if platform is Slack)",
            ),
        ),
        migrations.AlterField(
            model_name="botintegration",
            name="platform",
            field=models.IntegerField(
                choices=[
                    (1, "Facebook"),
                    (2, "Instagram & FB"),
                    (3, "Whatsapp"),
                    (4, "Slack"),
                ],
                help_text="The platform that the bot is integrated with",
            ),
        ),
        migrations.AddIndex(
            model_name="botintegration",
            index=models.Index(
                fields=["fb_page_id"], name="bots_botint_fb_page_d57a7d_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="botintegration",
            index=models.Index(
                fields=["ig_account_id"], name="bots_botint_ig_acco_071b67_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="botintegration",
            index=models.Index(
                fields=["wa_phone_number_id"], name="bots_botint_wa_phon_9a0bef_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="botintegration",
            index=models.Index(
                fields=["slack_channel_id"], name="bots_botint_slack_c_b566df_idx"
            ),
        ),
    ]
