from datetime import timedelta

from django.db.models import Case, CharField, When, Count, Value, Q
from django.db.models.functions import Now
from bots.models import SavedRun, Workflow


def get_status():
    # Assuming that your datetime fields are timezone aware
    # Adjust the following to fit your actual time zone handling
    one_day_ago = Now() - timedelta(days=1)

    # Building the Case statement for the status
    status_case = Case(
        When(run_status="", error_msg="", then=Value("success")),
        When(
            run_status="",
            error_msg__contains="rejected as a result of our safety system",
            then=Value("safety checker"),
        ),
        When(
            run_status="", error_msg__icontains="credit", then=Value("credit related")
        ),
        When(~Q(error_msg=""), run_status="", then=Value("failed")),
        default=Value("running"),
        output_field=CharField(),
    )

    # Query
    results = (
        SavedRun.objects.filter(created_at__gte=one_day_ago)
        .annotate(status=status_case)
        .values("workflow")
        .annotate(
            total=Count("id"),
            success=Count("id", filter=Q(status="success")),
            failed=Count("id", filter=Q(status="failed")),
            running=Count("id", filter=Q(status="running")),
            safety_check_failed=Count("id", filter=Q(status="safety checker")),
            credit_related=Count("id", filter=Q(status="credit related")),
            delayed_gt_5_minutes=Count(
                "id",
                filter=Q(
                    status="running", created_at__lte=Now() - timedelta(minutes=5)
                ),
            ),
            failed_lt_5_minutes=Count(
                "id",
                filter=Q(status="failed", updated_at__gte=Now() - timedelta(minutes=5)),
            ),
            other=Count("id", filter=Q(status="other")),
        )
        .order_by("workflow")
    )

    results = list(
        map(
            lambda row: {"workflow": Workflow(row.pop("workflow")).label, **row},
            results,
        )
    )

    return results
