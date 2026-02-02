from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bots", "0113_tag_publishedrun_tags_publishedrunversion_tags"),
    ]

    operations = [
        migrations.AddField(
            model_name="savedrun",
            name="error_params",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Structured error parameters for UI rendering or API responses.",
            ),
        ),
    ]
