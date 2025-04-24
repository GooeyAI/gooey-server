import gooey_gui as gui
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.models import (
    BooleanField,
    F,
    FilteredRelation,
    Q,
    QuerySet,
    Value,
)

from app_users.models import AppUser
from bots.models import PublishedRun, Workflow, WorkflowAccessLevel
from daras_ai_v2.grid_layout_widget import grid_layout
from widgets.saved_workflow import render_saved_workflow_preview
from workspaces.models import WorkspaceRole


def render_search_bar(key: str = "search_query", value: str = "") -> str:
    with (
        gui.styled(
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
        ),
        gui.div(),
    ):
        search_query = gui.text_input(
            "",
            placeholder="Search Workflows",
            className="bg-light border-0 rounded-pill",
            style=dict(maxWidth="500px", marginLeft="-0.3rem", paddingLeft="2.7rem"),
            key=key,
            value=value,
        )

    return search_query


def render_search_results(user: AppUser | None, search_query: str):
    qs = get_filtered_published_runs(user, search_query)
    qs = qs.select_related("workspace", "created_by", "saved_run")
    grid_layout(1, qs, _render_run)


def _render_run(pr: PublishedRun):
    workflow = Workflow(pr.workflow)
    render_saved_workflow_preview(
        workflow.page_cls,
        pr,
        workflow_pill=f"{workflow.get_or_create_metadata().emoji} {workflow.short_title}",
        hide_visibility_pill=True,
    )


def get_filtered_published_runs(user: AppUser | None, search_query: str) -> QuerySet:
    qs = PublishedRun.objects.all()
    qs = build_search_filter(qs, search_query)
    qs = build_workflow_access_filter(qs, user)
    qs = qs.annotate(
        is_root_workflow=Q(published_run_id=""),
    ).order_by(
        F("is_created_by").desc(nulls_last=True),
        "-is_member",
        "-is_approved_example",
        "-is_root_workflow",
        "-updated_at",
    )
    return qs[:25]


def build_workflow_access_filter(qs: QuerySet, user: AppUser | None) -> QuerySet:
    # a) everyone can see published examples
    workflow_access_filter = Q(
        public_access__gt=WorkflowAccessLevel.VIEW_ONLY, is_approved_example=True
    )
    if user and not user.is_anonymous:
        qs = qs.annotate(
            membership=FilteredRelation(
                "workspace__memberships",
                condition=Q(
                    workspace__memberships__user=user,
                    workspace__memberships__deleted__isnull=True,
                ),
            ),
            is_member=Q(membership__role__isnull=False),
            is_admin=Q(membership__role__in=[WorkspaceRole.ADMIN, WorkspaceRole.OWNER]),
            is_created_by=Q(created_by=user),
        )
        workflow_access_filter |= (
            #  b) creator always sees it
            Q(created_by=user)
            #  c) any member (role not null) *and* workspace_access > VIEW_ONLY
            | (
                Q(is_member=True)
                & Q(workspace_access__gt=WorkflowAccessLevel.VIEW_ONLY)
            )
            #  d) admin/owner always sees it
            | Q(is_admin=True)
        )
    else:
        qs = qs.annotate(
            is_created_by=Value(False, output_field=BooleanField()),
            is_member=Value(False, output_field=BooleanField()),
        )
    return qs.filter(workflow_access_filter)


def build_search_filter(qs: QuerySet, search_query: str) -> QuerySet:
    # build a raw tsquery like “foo:* & bar:*”
    tokens = [t for t in search_query.strip().split() if t]
    raw_query = " & ".join(f"{t}:*" for t in tokens)
    search = SearchQuery(raw_query, search_type="raw")

    # search by workflow title
    workflow_search = PublishedRun.objects.filter(
        published_run_id="", title__search=search
    ).values("workflow")

    # search by workflow metadata
    qs = qs.annotate(
        search=SearchVector(
            "title",
            "notes",
            "created_by__display_name",
            "workspace__handle__name",
            "workspace__name",
        ),
    )

    # filter on the search vector
    return qs.filter(Q(search=search) | Q(workflow__in=workflow_search))
