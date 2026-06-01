from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bots", "0120_tag_fa_icon_tag_color"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowmetadata",
            name="fa_icon",
            field=models.TextField(
                blank=True,
                default="",
                help_text='Font Awesome icon HTML, e.g. &lt;i class="fa-regular fa-tag"&gt;&lt;/i&gt;',
            ),
        ),
        migrations.AddField(
            model_name="workflowmetadata",
            name="color",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Hex color associated with this workflow, e.g. #4d8af0",
                max_length=32,
            ),
        ),
    ]
