# Generated by Django 4.2 on 2023-05-25 11:15

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bots", "0009_alter_feedback_options_conversation_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="feedback",
            name="category",
            field=models.IntegerField(
                choices=[
                    (1, "Unspecified"),
                    (2, "Incoming"),
                    (3, "Translation"),
                    (4, "Retrieval"),
                    (5, "Summarization"),
                    (6, "Translation of answer"),
                ],
                default=1,
            ),
        ),
        migrations.AddField(
            model_name="feedback",
            name="status",
            field=models.CharField(
                choices=[
                    (1, "Untriaged"),
                    (2, "Test"),
                    (3, "Needs investigation"),
                    (4, "Resolved"),
                ],
                default=1,
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="feedback",
            name="text_english",
            field=models.TextField(blank=True, default=""),
        ),
    ]
