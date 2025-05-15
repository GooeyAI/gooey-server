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
from pydantic import BaseModel, validator

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

    @validator("*")
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

    with (
        gui.styled(r"& .gui-input { margin-bottom: 0; }"),
        gui.div(),
        gui.div(className="d-lg-flex container-margin-reset gap-3"),
    ):
        with gui.div(className="col-lg-5 flex-grow-1 flex-lg-grow-0 mb-2 mb-lg-0"):
            search_query = render_search_bar(value=search_filters.search)

        with gui.div(className="col-lg-7 d-flex align-items-center gap-2 mw-100"):
            gui.caption(
                f'{icons.filter}<span class="d-none d-lg-inline"> Filter</span>',
                unsafe_allow_html=True,
            )
            with gui.div(
                className="d-flex gap-2 flex-grow-1",
                style={"maxWidth": "calc(100% - 24px)"},
            ):
                if current_user and not current_user.is_anonymous:
                    with gui.div(className="flex-grow-1", style={"maxWidth": "50%"}):
                        workspace_filter = render_workspace_filter(
                            current_user=current_user, value=search_filters.workspace
                        )
                else:
                    workspace_filter = None
                with gui.div(className="flex-grow-1", style={"maxWidth": "50%"}):
                    workflow_filter = render_workflow_filter(
                        value=search_filters.workflow
                    )

    return SearchFilters(
        search=search_query, workspace=workspace_filter, workflow=workflow_filter
    )


def render_popover_selector(options: dict[str, str], label: str, key: str, value: str):
    with (
        gui.styled(r"& > button { max-width: 100%; width: 100%; }"),
        gui.div(),
    ):
        popover, content = gui.popover(interactive=True, placement="bottom")

    with popover, gui.div(className="d-flex align-items-center p-2 border rounded"):
        popover_text = value and options.get(value) or label
        gui.html(
            popover_text,
            className="flex-grow-1 d-inline-block pe-2 border-end border-light-2 overflow-hidden text-truncate",
        )
        gui.html(icons.chevron_down, className="d-block ps-2")

    with (
        content,
        gui.div(
            className="d-flex flex-column bg-white border border-dark rounded shadow mx-2 overflow-auto",
            style={"maxWidth": "500px", "maxHeight": "500px"},
        ),
    ):
        for option_value, option_html in options.items():
            with gui.tag(
                "button",
                className="bg-transparent border-0 text-start bg-hover-light px-3 my-1",
                name=key,
                type="submit",
                value=option_value,
                style=dict(minHeight="2.2rem"),
            ):
                with gui.div(className="row align-items-center"):
                    with gui.div(className="col-10"):
                        gui.html(option_html)
                    with gui.div(className="col-2 text-end"):
                        if option_value == value:
                            gui.html(
                                '<i class="fa-sharp fa-solid fa-circle-check"></i>'
                            )

    return gui.session_state.pop(key, value)


def render_workspace_filter(
    current_user: AppUser | None = None, key: str = "workspace_filter", value: str = ""
) -> str | None:
    if not current_user or current_user.is_anonymous:
        return None

    workspace_options = {None: f"{icons.octopus}&nbsp;&nbsp;&nbsp;Any"}
    workspace_options |= {
        w.handle_id and w.handle.name or str(w.id): w.display_html(
            current_user=current_user, icon_size="20px"
        )
        for w in current_user.cached_workspaces
    }

    return render_popover_selector(
        workspace_options, label=f"{icons.octopus} Workspace", key=key, value=value
    )


def render_workflow_filter(key: str = "workflow_filter", value: str = "", **props):
    from daras_ai_v2.all_pages import all_home_pages

    workflow_options = {None: f"{icons.example}&nbsp;&nbsp;&nbsp;Any"}
    workflow_options |= {
        p.workflow.short_slug: f"{p.workflow.emoji} {p.workflow.short_title}"
        for p in all_home_pages
    }
    return render_popover_selector(
        workflow_options, label=f"{icons.example} Type", key=key, value=value, **props
    )


def render_search_bar(key: str = "search_query", value: str = "") -> str:
    with (
        gui.styled(
            r"""
        & {
            position: relative;
            max-width: 500px;
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


def render_search_results(user: AppUser | None, search_filters: SearchFilters):
    qs = get_filtered_published_runs(user, search_filters)
    qs = qs.select_related("workspace", "created_by", "saved_run")
    grid_layout(1, qs, _render_run)


def _render_run(pr: PublishedRun):
    workflow = Workflow(pr.workflow)
    render_saved_workflow_preview(
        workflow.page_cls,
        pr,
        workflow_pill=f"{workflow.get_or_create_metadata().emoji} {workflow.short_title}",
        hide_visibility_pill=True,
        show_workspace_author=True,
    )


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
            qs = qs.filter(workspace=int(search_filters.workspace))
        except ValueError:
            qs = qs.filter(workspace__handle__name=search_filters.workspace)
    if search_filters.workflow:
        workflow_page = page_slug_map[normalize_slug(search_filters.workflow)]
        qs = qs.filter(workflow=workflow_page.workflow.value)

    if search_filters.search:
        # build a raw tsquery like “foo:* & bar:*”
        tokens = [t for t in search_filters.search.strip().split() if t]
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
        qs = qs.filter(Q(search=search) | Q(workflow__in=workflow_search))

    return qs
