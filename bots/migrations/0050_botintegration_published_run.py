# Generated by Django 4.2.7 on 2023-12-05 13:39

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("bots", "0049_publishedrun_publishedrunversion"),
    ]

    operations = [
        migrations.AddField(
            model_name="botintegration",
            name="published_run",
            field=models.ForeignKey(
                blank=True,
                default=None,
                help_text="The saved run that the bot is based on",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="botintegrations",
                to="bots.publishedrun",
            ),
        ),
    ]
