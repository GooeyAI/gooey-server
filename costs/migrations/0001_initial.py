# Generated by Django 4.2.5 on 2024-01-04 03:59

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("bots", "0054_alter_savedrun_example_id_alter_savedrun_page_notes_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="UsageCost",
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
                    "provider",
                    models.IntegerField(
                        choices=[
                            (1, "OpenAI"),
                            (2, "GPT-4"),
                            (3, "dalle-e"),
                            (4, "whisper"),
                            (5, "GPT-3.5"),
                        ]
                    ),
                ),
                ("model", models.TextField(blank=True, verbose_name="model")),
                ("param", models.TextField(blank=True, verbose_name="param")),
                ("notes", models.TextField(blank=True, default="")),
                ("calculation_notes", models.TextField(blank=True, default="")),
                ("dollar_amt", models.DecimalField(decimal_places=8, max_digits=13)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "saved_run",
                    models.ForeignKey(
                        blank=True,
                        default=None,
                        help_text="The run that was last saved by the user.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="usage_costs",
                        to="bots.savedrun",
                    ),
                ),
            ],
        ),
    ]
