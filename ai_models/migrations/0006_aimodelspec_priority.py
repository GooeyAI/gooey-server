from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ai_models", "0005_aimodelspec_paid_only_alter_aimodelspec_provider"),
    ]

    operations = [
        migrations.AddField(
            model_name="aimodelspec",
            name="priority",
            field=models.IntegerField(
                default=1,
                help_text="Display priority for model lists. Higher numbers appear first; ties are sorted alphabetically.",
            ),
        ),
    ]
