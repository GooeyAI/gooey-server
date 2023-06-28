# Generated by Django 4.2 on 2023-05-30 19:22

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app_users", "0003_appuser_created_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="appuser",
            name="stripe_customer_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
