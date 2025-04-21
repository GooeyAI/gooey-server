from django.db.models import OuterRef, Count, Case, When
from django.db.models.functions import Coalesce

from bots.models import PublishedRun, SavedRun


def run():
    """
    Migrate run counts for existing PublishedRun objects by counting their children runs.
    """
    print("Starting migration of published run counts...")

    # Get all published runs
    qs = PublishedRun.objects.all()
    total = qs.count()
    print(f"Found {total} published runs to process")

    qs.update(
        run_count=Case(
            When(
                published_run_id="",
                then=SavedRun.objects.filter(workflow=OuterRef("workflow"))
                .values("workflow")
                .annotate(run_count=Count("pk"))
                .values("run_count")[:1],
            ),
            default=Coalesce(
                SavedRun.objects.filter(parent_version__published_run=OuterRef("pk"))
                .values("parent_version__published_run")
                .annotate(run_count=Count("pk"))
                .values("run_count")[:1],
                0,  # Default value if subquery returns null
            ),
        )
    )

    print("Migration completed successfully!")
