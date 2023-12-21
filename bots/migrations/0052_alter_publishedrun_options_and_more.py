# Generated by Django 4.2.7 on 2023-12-11 05:16

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bots", "0051_savedrun_parent_version"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="publishedrun",
            options={"get_latest_by": "updated_at", "ordering": ["-updated_at"]},
        ),
        migrations.AddIndex(
            model_name="publishedrun",
            index=models.Index(
                fields=["workflow"], name="bots_publis_workflo_a0953a_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="publishedrun",
            index=models.Index(
                fields=["workflow", "created_by"], name="bots_publis_workflo_c75a55_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="publishedrun",
            index=models.Index(
                fields=["workflow", "published_run_id"],
                name="bots_publis_workflo_87bece_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="publishedrun",
            index=models.Index(
                fields=["workflow", "visibility", "is_approved_example"],
                name="bots_publis_workflo_36a83a_idx",
            ),
        ),
    ]