# Generated by Django 4.2.5 on 2023-11-12 15:40

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bots", "0045_savedrun_transaction"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="savedrun",
            index=models.Index(
                fields=["-created_at"], name="bots_savedr_created_cb8e09_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="savedrun",
            index=models.Index(
                fields=["-updated_at"], name="bots_savedr_updated_a6c854_idx"
            ),
        ),
    ]
