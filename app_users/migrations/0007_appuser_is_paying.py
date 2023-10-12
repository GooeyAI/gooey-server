# Generated by Django 4.2.5 on 2023-10-12 13:54

from django.db import migrations, models


def set_is_paying_from_stripe_customer_id(apps, schema_editor):
    AppUser = apps.get_model("app_users", "appuser")
    AppUser.objects.exclude(stripe_customer_id="").update(is_paying=True)


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
