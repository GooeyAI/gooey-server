from html import escape as escape_html
from dataclasses import dataclass

from django.db.models import Count

import gooey_ui as st
from daras_ai_v2.base import format_number_with_suffix
from bots.models import PublishedRunVersion, SavedRun, Workflow
from app_users.models import AppUser


@dataclass
class ContributionsSummary:
    total: int
    top_contributions: dict[Workflow, int]  # sorted dict


def user_profile_page(user: AppUser):
    user_profile_header(user)


def user_profile_header(user: AppUser):
    with st.div(className="mt-3"):
        col1, col2 = st.columns([2, 10])

    with col1, st.div(
        className="d-flex justify-content-center align-items-center h-100"
    ):
        st.image(
            user.photo_url or "https://via.placeholder.com/128",
            style={"width": "150px", "height": "150px"},
            className="rounded-circle me-0 me-lg-3 mb-3 mb-lg-0",
        )

    run_icon = '<i class="fa-regular fa-person-running"></i>'
    run_count = get_run_count(user)
    contribs = get_contributions_summary(user)

    with col2, st.div(
        className="d-flex flex-column justify-content-center align-items-center align-items-lg-start"
    ):
        st.html(
            f"""\
<h1 class="m-0">{escape_html(user.display_name)}</h1>

<p class="lead text-secondary mb-0">{escape_html(user.handle and user.handle.name or "")}</p>

<div class="d-flex mt-3">
    <div class="me-3 text-secondary">
        {run_icon} {escape_html(format_number_with_suffix(run_count))} runs
    </div>

    <div>
        <div>{contribs.total} contributions since joining</div>
        <small class="mt-1">
            {", ".join(
                f"{escape_html(workflow.short_title)} ({count})"
                for workflow, count in contribs.top_contributions.items()
            )}
        </small>
    </div>
</div>
"""
        )


def get_run_count(user: AppUser) -> int:
    return SavedRun.objects.filter(uid=user.uid).count()


def get_contributions_summary(user: AppUser, *, top_n: int = 3) -> ContributionsSummary:
    count_by_workflow = (
        PublishedRunVersion.objects.filter(changed_by=user)
        .values("published_run__workflow")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    total = sum(row["count"] for row in count_by_workflow)
    top_contributions = {
        Workflow(row["published_run__workflow"]): row["count"]
        for row in count_by_workflow[:top_n]
    }

    return ContributionsSummary(total=total, top_contributions=top_contributions)
