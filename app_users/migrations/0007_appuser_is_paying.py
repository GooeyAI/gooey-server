# Generated by Django 4.2.5 on 2023-10-12 13:54

from django.db import migrations, models


def set_is_paying_from_stripe_customer_id(apps, schema_editor):
    AppUsers = apps.get_model("app_users", "appuser")
    for user in AppUsers.objects.all():
        user.is_paying = bool(user.stripe_customer_id)
        user.save()


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
        migrations.RunPython(set_is_paying_from_stripe_customer_id),
    ]
