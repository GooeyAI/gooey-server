import gooey_gui as gui
from django.contrib.postgres.search import SearchVector
from django.db.models import Q, QuerySet

from app_users.models import AppUser
from bots.models import WorkflowAccessLevel, PublishedRun, Workflow
from daras_ai_v2.grid_layout_widget import grid_layout
from widgets.saved_workflow import render_saved_workflow_preview


def render_search_bar(key: str = "search_query") -> str:
    with gui.styled(
        r"""
        & {
            position: relative;
        }
        &::before {
            content: "\f002";              /* FontAwesome glyph */
            font-family: "Font Awesome 6 Pro";    
            position: absolute;
            left: 12px;                  
            top: 50%;
            transform: translateY(-50%);
            pointer-events: none;          /* let clicks go through to the input */
            color: #888;
            font-size: 0.9em;
        }
        """
    ), gui.div():
        search_query = gui.text_input(
            "",
            placeholder="Search Workflows",
            className="bg-light border-0 rounded-pill",
            style=dict(maxWidth="500px", marginLeft="-0.3rem", paddingLeft="2.7rem"),
            key=key,
        )

    return search_query


def render_search_results(search_query: str, user: AppUser):
    qs = get_filtered_published_runs(search_query, user)
    grid_layout(1, qs, _render_run)


def _render_run(pr: PublishedRun):
    workflow = Workflow(pr.workflow)
    render_saved_workflow_preview(
        workflow.page_cls,
        pr,
        workflow_pill=f"{workflow.get_or_create_metadata().emoji} {workflow.short_title}",
    )


def get_filtered_published_runs(search_query: str, user: AppUser) -> QuerySet:
    qs = (
        PublishedRun.objects.select_related("workspace", "created_by", "saved_run")
        .annotate(
            search=SearchVector(
                "title", "notes", "created_by__display_name", "workspace__name"
            ),
            is_personal_workflow=Q(created_by=user),
            is_team_workflow=Q(workspace__memberships__user=user),
            is_root_workflow=Q(published_run_id=""),
        )
        .order_by(
            "is_personal_workflow",
            "is_team_workflow",
            "is_approved_example",
            "is_root_workflow",
            "-updated_at",
        )
    )

    workflow_search = PublishedRun.objects.filter(
        published_run_id="", title__search=search_query
    ).values("workflow")
    search_filter = Q(search=search_query) | Q(workflow__in=workflow_search)

    permission_filter = ~Q(public_access=WorkflowAccessLevel.VIEW_ONLY)
    if user and not user.is_anonymous:
        permission_filter |= Q(created_by=user)
        permission_filter |= Q(
            workspace__memberships__user=user,
            workspace__memberships__deleted__isnull=True,
        ) & ~Q(workspace_access=WorkflowAccessLevel.VIEW_ONLY)

    qs = qs.filter(search_filter & permission_filter)[:25]
    return qs
