# Generated by Django 4.2.5 on 2023-11-07 15:33

import bots.custom_fields
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("files", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="GlossaryResource",
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
                    "f_url",
                    bots.custom_fields.CustomURLField(
                        max_length=2048, unique=True, verbose_name="File URL"
                    ),
                ),
                ("language_codes", models.JSONField(default=list)),
                ("glossary_url", bots.custom_fields.CustomURLField(max_length=2048)),
                (
                    "glossary_id",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("project_id", models.CharField(default="dara-c1b52", max_length=100)),
                ("location", models.CharField(default="us-central1", max_length=100)),
                ("usage_count", models.IntegerField(default=0)),
                ("last_updated", models.DateTimeField(auto_now=True)),
                (
                    "metadata",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="glossary_resources",
                        to="files.filemetadata",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["usage_count", "last_updated"],
                        name="glossary_re_usage_c_d82f17_idx",
                    )
                ],
            },
        ),
    ]
