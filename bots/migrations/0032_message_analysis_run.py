# Generated by Django 4.2.3 on 2023-08-23 19:50

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("bots", "0031_message_analysis_result_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="analysis_run",
            field=models.ForeignKey(
                blank=True,
                default=None,
                help_text="The analysis run that generated this message",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="analysis_messages",
                to="bots.savedrun",
            ),
        ),
    ]
