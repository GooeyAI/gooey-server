# Generated by Django 4.2.5 on 2023-11-20 18:23

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("app_users", "0009_alter_appusertransaction_options_and_more"),
        ("bots", "0045_savedrun_transaction"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserSecret",
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
                    "name",
                    models.CharField(
                        help_text="Name of the secret key to refer this by",
                        max_length=256,
                        validators=[
                            django.core.validators.RegexValidator(
                                message="Valid names can only contain alphanumeric characters, -, and _.",
                                regex="^[a-zA-Z0-9_-]+$",
                            )
                        ],
                    ),
                ),
                (
                    "provider",
                    models.IntegerField(
                        choices=[(1, "Eleven Labs")],
                        help_text="The secret key provider where you can use this key",
                    ),
                ),
                (
                    "preview",
                    models.CharField(
                        help_text="Preview for the secret key", max_length=10
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True, default="", help_text="More details about this key"
                    ),
                ),
                (
                    "gcp_secret_id",
                    models.CharField(
                        help_text="Lookup Key in GCP Secret Manager", max_length=63
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="secrets",
                        to="app_users.appuser",
                    ),
                ),
            ],
            options={
                "unique_together": {("user", "name")},
            },
        ),
    ]
