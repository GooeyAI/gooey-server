# Generated by Django 4.2 on 2023-04-26 17:14

from django.db import migrations, models
import gooeysite.custom_fields


class Migration(migrations.Migration):
    dependencies = [
        ("bots", "0002_rename_page_access_token_bot_fb_page_access_token_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="gooey_url",
            field=gooeysite.custom_fields.CustomURLField(default=None, max_length=2048),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="bot",
            name="user_language",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AlterField(
            model_name="message",
            name="role",
            field=models.CharField(
                choices=[("user", "User"), ("asisstant", "Asisstant")], max_length=10
            ),
        ),
    ]
