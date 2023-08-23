# Generated by Django 4.2.3 on 2023-08-23 22:59

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("bots", "0034_alter_savedrun_example_id_alter_savedrun_run_id_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="botintegration",
            options={"ordering": ["-updated_at"]},
        ),
        migrations.AddField(
            model_name="botintegration",
            name="analysis_run",
            field=models.ForeignKey(
                blank=True,
                default=None,
                help_text="Use this saved run for analysis",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="analysis_botintegrations",
                to="bots.savedrun",
            ),
        ),
        migrations.AlterField(
            model_name="botintegration",
            name="enable_analysis",
            field=models.BooleanField(
                default=False, help_text="Enable analysis for this bot (DEPRECATED)"
            ),
        ),
    ]
