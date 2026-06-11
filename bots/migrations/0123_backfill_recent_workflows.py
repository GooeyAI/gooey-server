from django.db import migrations

# For each (workspace, uid, published_run), pick that user's most-recent run of
# the workflow (DISTINCT ON + ORDER BY updated_at DESC) and seed one row. The
# inner join to publishedrunversion restricts to runs created from a published
# run, mirroring the old `parent_version__published_run__isnull=False` filter.
BACKFILL_SQL = """
INSERT INTO bots_workspacerecentworkflow
    (workspace_id, uid, published_run_id, last_saved_run_id, last_used_at)
SELECT DISTINCT ON (sr.workspace_id, sr.uid, prv.published_run_id)
    sr.workspace_id, sr.uid, prv.published_run_id, sr.id, sr.updated_at
FROM bots_savedrun sr
JOIN bots_publishedrunversion prv ON prv.id = sr.parent_version_id
WHERE sr.workspace_id IS NOT NULL
ORDER BY sr.workspace_id, sr.uid, prv.published_run_id, sr.updated_at DESC
ON CONFLICT DO NOTHING;
"""


def backfill_recent_workflows(apps, schema_editor):
    schema_editor.execute(BACKFILL_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("bots", "0122_recent_workflow"),
    ]

    operations = [
        # reverse is a noop: rows are indistinguishable from ones the live
        # upsert hook writes, so we never delete on unapply. ON CONFLICT keeps
        # a re-run idempotent.
        migrations.RunPython(
            backfill_recent_workflows,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
