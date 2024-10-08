# Generated by Django 4.2.3 on 2023-07-27 20:24

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bots", "0025_alter_savedrun_created_at_alter_savedrun_updated_at"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="savedrun",
            unique_together=set(),
        ),
        migrations.AlterField(
            model_name="savedrun",
            name="example_id",
            field=models.TextField(blank=True, default=None, null=True),
        ),
        migrations.AlterField(
            model_name="savedrun",
            name="run_id",
            field=models.TextField(blank=True, default=None, null=True),
        ),
        migrations.AlterField(
            model_name="savedrun",
            name="uid",
            field=models.TextField(blank=True, default=None, null=True),
        ),
    ]
