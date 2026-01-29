from django.db import migrations, models
from django.utils.text import slugify


def backfill_tool_name(apps, schema_editor):
    CalledFunction = apps.get_model("functions", "CalledFunction")

    qs = (
        CalledFunction.objects.filter(tool_name="")
        .select_related("function_run__parent_version__published_run")
        .only("id", "tool_name", "function_run")
    )

    updates = []
    batch_size = 500
    for called_fn in qs.iterator():
        fn_sr = called_fn.function_run
        pr = fn_sr and fn_sr.parent_version and fn_sr.parent_version.published_run
        title = pr and pr.title
        if not title:
            continue
        called_fn.tool_name = slugify(title).replace("-", "_")
        updates.append(called_fn)
        if len(updates) >= batch_size:
            CalledFunction.objects.bulk_update(updates, ["tool_name"])
            updates.clear()

    if updates:
        CalledFunction.objects.bulk_update(updates, ["tool_name"])


class Migration(migrations.Migration):
    dependencies = [
        ("functions", "0004_alter_calledfunction_trigger"),
    ]

    operations = [
        migrations.AddField(
            model_name="calledfunction",
            name="tool_name",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.RunPython(backfill_tool_name, migrations.RunPython.noop),
    ]
