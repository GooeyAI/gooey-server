# Generated by Django 4.2.5 on 2023-12-27 17:54

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app_users", "0012_alter_appusertransaction_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="appusertransaction",
            name="type",
            field=models.CharField(default="Stripe", max_length=255),
        ),
    ]
