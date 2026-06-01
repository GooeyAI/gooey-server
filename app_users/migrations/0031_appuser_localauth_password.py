from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_users", "0030_appuser_last_login_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="appuser",
            name="localauth_password",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
