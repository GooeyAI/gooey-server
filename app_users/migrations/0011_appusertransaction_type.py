# Generated by Django 4.2.5 on 2023-12-27 17:31

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app_users", "0010_alter_appuser_balance_alter_appuser_created_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="appusertransaction",
            name="type",
            field=models.CharField(default="Stripe", max_length=255),
        ),
    ]
