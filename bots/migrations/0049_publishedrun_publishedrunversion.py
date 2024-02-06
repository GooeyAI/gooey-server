# Generated by Django 4.2.7 on 2023-12-05 13:39

from django.db import migrations, models
import django.db.models.deletion

from bots.models import PublishedRunVisibility
from daras_ai_v2.crypto import get_random_doc_id


def set_field_attribute(instance, field_name, **attrs):
    for field in instance._meta.local_fields:
        if field.name == field_name:
            for attr, value in attrs.items():
                setattr(field, attr, value)


def create_published_run_from_example(
    *,
    published_run_model,
    published_run_version_model,
    saved_run,
    user,
    published_run_id,
):
    published_run = published_run_model(
        workflow=saved_run.workflow,
        published_run_id=published_run_id,
        created_by=user,
        last_edited_by=user,
        saved_run=saved_run,
        title=saved_run.page_title,
        notes=saved_run.page_notes,
        visibility=PublishedRunVisibility.PUBLIC,
        is_approved_example=not saved_run.hidden,
    )
    set_field_attribute(published_run, "created_at", auto_now_add=False)
    set_field_attribute(published_run, "updated_at", auto_now=False)
    published_run.created_at = saved_run.created_at
    published_run.updated_at = saved_run.updated_at
    published_run.save()
    set_field_attribute(published_run, "created_at", auto_now_add=True)
    set_field_attribute(published_run, "updated_at", auto_now=True)

    version = published_run_version_model(
        published_run=published_run,
        version_id=get_random_doc_id(),
        saved_run=saved_run,
        changed_by=user,
        title=saved_run.page_title,
        notes=saved_run.page_notes,
        visibility=PublishedRunVisibility.PUBLIC,
    )
    set_field_attribute(published_run, "created_at", auto_now_add=False)
    version.created_at = saved_run.updated_at
    version.save()
    set_field_attribute(published_run, "created_at", auto_now_add=True)

    return published_run


def forwards_func(apps, schema_editor):
    # if example_id is not null, create published run with
    # is_approved_example to True and visibility to Public
    saved_run_model = apps.get_model("bots", "SavedRun")
    published_run_model = apps.get_model("bots", "PublishedRun")
    published_run_version_model = apps.get_model("bots", "PublishedRunVersion")
    db_alias = schema_editor.connection.alias

    # all examples
    for saved_run in saved_run_model.objects.using(db_alias).filter(
        example_id__isnull=False,
    ):
        create_published_run_from_example(
            published_run_model=published_run_model,
            published_run_version_model=published_run_version_model,
            saved_run=saved_run,
            user=None,  # TODO: use gooey-support user instead?
            published_run_id=saved_run.example_id,
        )

    # recipe root examples
    for saved_run in saved_run_model.objects.using(db_alias).filter(
        example_id__isnull=True,
        run_id__isnull=True,
        uid__isnull=True,
    ):
        create_published_run_from_example(
            published_run_model=published_run_model,
            published_run_version_model=published_run_version_model,
            saved_run=saved_run,
            user=None,
            published_run_id="",
        )


def backwards_func(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("app_users", "0010_alter_appuser_balance_alter_appuser_created_at_and_more"),
        ("bots", "0048_alter_messageattachment_url"),
    ]

    operations = [
        migrations.CreateModel(
            name="PublishedRun",
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
                ("published_run_id", models.CharField(blank=True, max_length=128)),
                (
                    "workflow",
                    models.IntegerField(
                        choices=[
                            (1, "Doc Search"),
                            (2, "Doc Summary"),
                            (3, "Google GPT"),
                            (4, "Copilot"),
                            (5, "Lipysnc + TTS"),
                            (6, "Text to Speech"),
                            (7, "Speech Recognition"),
                            (8, "Lipsync"),
                            (9, "Deforum Animation"),
                            (10, "Compare Text2Img"),
                            (11, "Text2Audio"),
                            (12, "Img2Img"),
                            (13, "Face Inpainting"),
                            (14, "Google Image Gen"),
                            (15, "Compare AI Upscalers"),
                            (16, "SEO Summary"),
                            (17, "Email Face Inpainting"),
                            (18, "Social Lookup Email"),
                            (19, "Object Inpainting"),
                            (20, "Image Segmentation"),
                            (21, "Compare LLM"),
                            (22, "Chyron Plant"),
                            (23, "Letter Writer"),
                            (24, "Smart GPT"),
                            (25, "AI QR Code"),
                            (26, "Doc Extract"),
                            (27, "Related QnA Maker"),
                            (28, "Related QnA Maker Doc"),
                            (29, "Embeddings"),
                            (30, "Bulk Runner"),
                        ]
                    ),
                ),
                ("title", models.TextField(blank=True, default="")),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "visibility",
                    models.IntegerField(
                        choices=[(1, "Unlisted"), (2, "Public")], default=1
                    ),
                ),
                ("is_approved_example", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="published_runs",
                        to="app_users.appuser",
                    ),
                ),
                (
                    "last_edited_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="app_users.appuser",
                    ),
                ),
                (
                    "saved_run",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="published_runs",
                        to="bots.savedrun",
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
                "unique_together": {("workflow", "published_run_id")},
            },
        ),
        migrations.CreateModel(
            name="PublishedRunVersion",
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
                ("version_id", models.CharField(max_length=128, unique=True)),
                ("title", models.TextField(blank=True, default="")),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "visibility",
                    models.IntegerField(
                        choices=[(1, "Unlisted"), (2, "Public")], default=1
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "changed_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="app_users.appuser",
                    ),
                ),
                (
                    "published_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versions",
                        to="bots.publishedrun",
                    ),
                ),
                (
                    "saved_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="published_run_versions",
                        to="bots.savedrun",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "get_latest_by": "created_at",
                "indexes": [
                    models.Index(
                        fields=["published_run", "-created_at"],
                        name="bots_publis_publish_9cd246_idx",
                    ),
                    models.Index(
                        fields=["version_id"], name="bots_publis_version_c121d4_idx"
                    ),
                ],
            },
        ),
        migrations.RunPython(
            forwards_func,
            backwards_func,
        ),
    ]
