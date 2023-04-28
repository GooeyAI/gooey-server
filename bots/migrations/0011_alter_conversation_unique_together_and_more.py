# Generated by Django 4.2 on 2023-04-27 20:02

from django.db import migrations, models
import gooeysite.custom_fields
import phonenumber_field.modelfields


class Migration(migrations.Migration):
    dependencies = [
        ("bots", "0010_botintegration_wa_phone_number_id_and_more"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="conversation",
            unique_together=set(),
        ),
        migrations.AddField(
            model_name="conversation",
            name="fb_page_access_token",
            field=models.TextField(
                blank=True,
                default="",
                editable=False,
                help_text="User's Facebook page access token (required if platform is Facebook/Instagram)",
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="fb_page_id",
            field=models.TextField(
                blank=True,
                db_index=True,
                default="",
                help_text="User's Facebook page id (required if platform is Facebook/Instagram)",
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="fb_page_name",
            field=models.TextField(
                blank=True,
                default="",
                help_text="User's Facebook page name (only for display)",
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="ig_account_id",
            field=models.TextField(
                blank=True,
                db_index=True,
                default="",
                help_text="User's Instagram account id (required if platform is Instagram)",
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="ig_username",
            field=models.TextField(
                blank=True,
                default="",
                help_text="User's Instagram username (only for display)",
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="wa_phone_number",
            field=phonenumber_field.modelfields.PhoneNumberField(
                blank=True,
                default="",
                help_text="User's WhatsApp phone number (only for display)",
                max_length=128,
                region=None,
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="wa_phone_number_id",
            field=models.TextField(
                blank=True,
                db_index=True,
                default="",
                help_text="User's WhatsApp phone number id (required if platform is WhatsApp)",
            ),
        ),
        migrations.AlterField(
            model_name="botintegration",
            name="app_url",
            field=gooeysite.custom_fields.CustomURLField(
                help_text="The gooey run url / example url / recipe url of the bot",
                max_length=2048,
            ),
        ),
        migrations.AlterField(
            model_name="botintegration",
            name="fb_page_access_token",
            field=models.TextField(
                blank=True,
                default="",
                editable=False,
                help_text="Bot's Facebook page access token (required if platform is Facebook/Instagram)",
            ),
        ),
        migrations.AlterField(
            model_name="botintegration",
            name="fb_page_id",
            field=models.TextField(
                blank=True,
                default=None,
                help_text="Bot's Facebook page id (required if platform is Facebook/Instagram)",
                null=True,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="botintegration",
            name="fb_page_name",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Bot's Facebook page name (only for display)",
            ),
        ),
        migrations.AlterField(
            model_name="botintegration",
            name="ig_account_id",
            field=models.TextField(
                blank=True,
                default=None,
                help_text="Bot's Instagram account id (required if platform is Instagram)",
                null=True,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="botintegration",
            name="ig_username",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Bot's Instagram username (only for display)",
            ),
        ),
        migrations.AlterField(
            model_name="botintegration",
            name="platform",
            field=models.IntegerField(
                choices=[(1, "Facebook"), (2, "Instagram & FB"), (3, "Whatsapp")],
                db_index=True,
                help_text="The platform that the bot is integrated with",
            ),
        ),
        migrations.AlterField(
            model_name="botintegration",
            name="show_feedback_buttons",
            field=models.BooleanField(
                default=False, help_text="Show 👍/👎 buttons with every response"
            ),
        ),
        migrations.AlterField(
            model_name="botintegration",
            name="wa_phone_number",
            field=phonenumber_field.modelfields.PhoneNumberField(
                blank=True,
                default="",
                help_text="Bot's WhatsApp phone number (only for display)",
                max_length=128,
                region=None,
            ),
        ),
        migrations.AlterField(
            model_name="botintegration",
            name="wa_phone_number_id",
            field=models.TextField(
                blank=True,
                default=None,
                help_text="Bot's WhatsApp phone number id (required if platform is WhatsApp)",
                null=True,
                unique=True,
            ),
        ),
        migrations.RemoveField(
            model_name="conversation",
            name="platform",
        ),
        migrations.RemoveField(
            model_name="conversation",
            name="user_id",
        ),
        migrations.RemoveField(
            model_name="conversation",
            name="user_phone_number",
        ),
    ]
