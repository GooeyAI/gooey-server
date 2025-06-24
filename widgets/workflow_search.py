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
from pydantic import BaseModel, field_validator

from app_users.models import AppUser
from bots.models import PublishedRun, Workflow, WorkflowAccessLevel
from daras_ai_v2 import icons
from daras_ai_v2.grid_layout_widget import grid_layout
from widgets.saved_workflow import render_saved_workflow_preview
from workspaces.models import WorkspaceRole


class SearchFilters(BaseModel):
    search: str | None = None
    workspace: str | None = None
    workflow: str | None = None

    @field_validator("*", mode="after")
    @classmethod
    def empty_str_to_none(cls, v: str | None) -> str | None:
        # to clear query params from URL when they are empty
        if v == "":
            return None
        return v

    def __bool__(self):
        return bool(self.search or self.workspace or self.workflow)


def render_search_filters(
    current_user: AppUser | None = None, search_filters: SearchFilters | None = None
):
    if not search_filters:
        search_filters = SearchFilters()

    with gui.div(className="d-lg-flex container-margin-reset gap-3"):
        with gui.div(className="col-lg-5 mb-2 mb-lg-0"):
            search_query = render_search_bar(value=search_filters.search)

        with gui.div(className="col-lg-7 d-flex align-items-center gap-2 mw-100"):
            gui.caption(
                f'{icons.filter}<span class="d-none d-lg-inline"> Filter</span>',
                unsafe_allow_html=True,
                className="text-nowrap text-muted",
            )
            with gui.div(className="flex-grow-1 d-flex gap-2 me-2 me-lg-4"):
                is_logged_in = current_user and not current_user.is_anonymous
                if is_logged_in:
                    with gui.div(className="col-6"):
                        workspace_filter = render_workspace_filter(
                            current_user=current_user, value=search_filters.workspace
                        )
                else:
                    workspace_filter = None
                with gui.div(className="col-6" if is_logged_in else "col-12 col-lg-6"):
                    workflow_filter = render_workflow_filter(
                        value=search_filters.workflow
                    )

    return SearchFilters(
        search=search_query, workspace=workspace_filter, workflow=workflow_filter
    )


def render_search_bar(key: str = "search_query", value: str = "") -> str:
    with (
        gui.styled(
            r"""
            & {
                position: relative;
            }
            & .gui-input {
                margin: 0;
                width: 100%;
            }
            & .clear_button {
                position: absolute;
                top: 14px;
                right: 18px;
                font-size: 0.9em;
                margin: 0 !important;
            }
            &::before {
                content: "\f002";              /* FontAwesome glyph */
                font-family: "Font Awesome 6 Pro";
                position: absolute;
                top: 14px;
                left: 18px;
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
            style=dict(resize="none", paddingLeft="2.7rem", paddingRight="2.7rem"),
            key=key,
            value=value,
        )
        if search_query and gui.button(
            icons.cancel, type="link", className="clear_button"
        ):
            gui.session_state[key] = ""
            search_query = ""

    return search_query


def render_workspace_filter(
    current_user: AppUser | None = None, key: str = "workspace_filter", value: str = ""
) -> str | None:
    if not current_user or current_user.is_anonymous:
        return None

    workspace_options = {
        w.handle_id and w.handle.name or str(w.id): w.display_html(
            current_user=current_user, icon_size="20px"
        )
        for w in current_user.cached_workspaces
    }

    return _render_selectbox(
        workspace_options,
        label=f"{icons.octopus} Workspace",
        key=key,
        value=value,
        blank_label=f"{icons.octopus}&nbsp; Any",
    )


def render_workflow_filter(key: str = "workflow_filter", value: str = ""):
    from daras_ai_v2.all_pages import all_home_pages

    workflow_options = {
        p.workflow.short_slug: f"{p.workflow.emoji} {p.workflow.short_title}"
        for p in all_home_pages
    }
    return _render_selectbox(
        workflow_options,
        label=f"{icons.example} Type",
        key=key,
        value=value,
        blank_label=f"{icons.example}&nbsp; Any",
    )


def _render_selectbox(
    options: dict[str, str],
    label: str,
    key: str,
    value: str,
    blank_label: str = "Any",
):
    return gui.selectbox(
        label="",
        label_visibility="collapsed",
        placeholder=label,
        options=options.keys(),
        key=key,
        value=value,
        allow_none=True,
        format_func=lambda x: options.get(x, blank_label),
        className="mb-0 text-nowrap",
        isClearable=True,
    )


def render_search_results(user: AppUser | None, search_filters: SearchFilters):
    qs = get_filtered_published_runs(user, search_filters)
    qs = qs.select_related("workspace", "created_by", "saved_run")

    def _render_run(pr: PublishedRun):
        workflow = Workflow(pr.workflow)

        # decide if workspace pill should be shown
        show_workspace_author = not bool(search_filters and search_filters.workspace)

        is_member = bool(getattr(pr, "is_member", False))
        hide_last_editor = bool(pr.workspace_id and not is_member)
        hide_updated_at = hide_last_editor

        # Only show all run counts if user is a member AND they're filtering by their workspace
        show_all_run_counts = False
        if is_member and search_filters and search_filters.workspace:
            if user and not user.is_anonymous:
                user_workspace_ids = {w.id for w in user.cached_workspaces}
                user_workspace_handles = {
                    w.handle.name for w in user.cached_workspaces if w.handle
                }

                try:
                    # Check if workspace filter is numeric (workspace ID)
                    workspace_id = int(search_filters.workspace)
                    show_all_run_counts = workspace_id in user_workspace_ids
                except ValueError:
                    # Workspace filter is a handle name
                    show_all_run_counts = (
                        search_filters.workspace in user_workspace_handles
                    )

        render_saved_workflow_preview(
            workflow.page_cls,
            pr,
            workflow_pill=f"{workflow.get_or_create_metadata().emoji} {workflow.short_title}",
            hide_visibility_pill=True,
            show_workspace_author=show_workspace_author,
            hide_last_editor=hide_last_editor,
            hide_updated_at=hide_updated_at,
            show_all_run_counts=show_all_run_counts,
        )

    grid_layout(1, qs, _render_run)


def get_filtered_published_runs(
    user: AppUser | None, search_filters: SearchFilters
) -> QuerySet:
    qs = PublishedRun.objects.all()
    qs = build_search_filter(qs, search_filters)
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


def build_search_filter(qs: QuerySet, search_filters: SearchFilters) -> QuerySet:
    from daras_ai_v2.all_pages import page_slug_map, normalize_slug

    if search_filters.workspace:
        try:
            workspace = int(search_filters.workspace)
        except ValueError:
            qs = qs.filter(workspace__handle__name=search_filters.workspace)
        else:
            qs = qs.filter(workspace=workspace)

    if search_filters.workflow:
        try:
            workflow_page = page_slug_map[normalize_slug(search_filters.workflow)]
        except KeyError:
            pass
        else:
            qs = qs.filter(workflow=workflow_page.workflow.value)

    if search_filters.search:
        # build a raw tsquery like "foo:* & bar:*
        tokens = []
        for token in search_filters.search.strip().split():
            # Only allow tokens that are alphanumeric
            token = "".join(c for c in token if c.isalnum())
            if not token:
                continue
            tokens.append(token + ":*")
        raw_query = " & ".join(tokens)
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
        qs = qs.filter(Q(search=search) | Q(workflow__in=workflow_search))

    return qs
