from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bots", "0116_botintegration_telegram_bot_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="savedrun",
            name="cancelled",
            field=models.BooleanField(default=False),
        ),
    ]
