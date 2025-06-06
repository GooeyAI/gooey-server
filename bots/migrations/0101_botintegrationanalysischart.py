# Generated by Django 5.1.3 on 2025-04-27 00:58

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bots", "0100_remove_publishedrun_publishedrun_search_vector_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="BotIntegrationAnalysisChart",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "result_field",
                    models.TextField(
                        help_text="The analysis result JSON field to visualize"
                    ),
                ),
                (
                    "graph_type",
                    models.IntegerField(
                        choices=[
                            (1, "Display as Text"),
                            (2, "Table of Counts"),
                            (3, "Bar Chart of Counts"),
                            (4, "Pie Chart of Counts"),
                            (5, "Radar Plot of Counts"),
                        ],
                        help_text="Type of graph to display",
                    ),
                ),
                (
                    "data_selection",
                    models.IntegerField(
                        choices=[
                            (1, "All Data"),
                            (2, "Last Analysis"),
                            (3, "Last Analysis per Conversation"),
                        ],
                        help_text="Data selection mode",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "bot_integration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="analysis_charts",
                        to="bots.botintegration",
                    ),
                ),
            ],
        ),
    ]
