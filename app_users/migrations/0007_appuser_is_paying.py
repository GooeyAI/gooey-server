# Generated by Django 4.2.5 on 2023-10-12 13:54

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app_users", "0006_appuser_disable_safety_checker"),
    ]

    operations = [
        migrations.AddField(
            model_name="appuser",
            name="is_paying",
            field=models.BooleanField(default=False),
        ),
    ]
