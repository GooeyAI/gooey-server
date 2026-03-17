from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("bots", "0114_savedrun_error_params"),
    ]

    operations = [
        migrations.AddField(
            model_name="savedrun",
            name="gooey_builder_conversation",
            field=models.ForeignKey(
                blank=True,
                default=None,
                help_text="The Gooey Builder conversation that triggered this run.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="builder_created_runs",
                to="bots.conversation",
            ),
        ),
    ]
