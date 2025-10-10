import re
import typing

import gooey_gui as gui
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import (
    BooleanField,
    F,
    FilteredRelation,
    Q,
    OrderBy,
    QuerySet,
    Value,
)
from django.utils.translation import ngettext
from pydantic import BaseModel, field_validator

from app_users.models import AppUser
from bots.models import PublishedRun, Tag, WorkflowAccessLevel
from daras_ai_v2 import icons
from daras_ai_v2.custom_enum import GooeyEnum
from daras_ai_v2.fastapi_tricks import get_app_route_url
from daras_ai_v2.grid_layout_widget import grid_layout
from widgets.saved_workflow import render_pill_with_link, render_saved_workflow_preview
from workspaces.models import Workspace, WorkspaceRole

if typing.TYPE_CHECKING:
    from fastapi import Request


class SortOption(typing.NamedTuple):
    label: str
    icon: str


_icon_width = "1.3em"


class SortOptions(SortOption, GooeyEnum):
    featured = SortOption(
        label="Featured",
        icon=f'<i class="fa-solid fa-star" style="width: {_icon_width};"></i>',
    )
    last_updated = SortOption(
        label="Last Updated",
        icon=f'<i class="fa-solid fa-clock" style="width: {_icon_width};"></i>',
    )
    created_at = SortOption(
        label="Created At",
        icon=f'<i class="fa-solid fa-calendar" style="width: {_icon_width};"></i>',
    )
    most_runs = SortOption(
        label="Most Runs",
        icon=f'<i class="fa-solid fa-chart-line" style="width: {_icon_width};"></i>',
    )

    @classmethod
    def get(cls, key=None):
        return super().get(key, default=cls.featured)

    def html_icon_label(self) -> str:
        return f'{self.icon}<span class="hide-on-small-screens"> {self.label}</span>'


SEARCH_TOKEN_ALLOWED_CHARS = re.compile(r"[\w]+")


class SearchFilters(BaseModel):
    search: str = ""
    workspace: str = ""
    workflow: str = ""
    sort: str = ""

    def __bool__(self):
        return bool(self.search or self.workspace or self.workflow or self.sort)

    @field_validator("sort", "workflow", mode="before")
    @classmethod
    def to_lower(cls, v):
        return v.lower() if isinstance(v, str) else v

    def get_query_params(self) -> dict[str, str]:
        return self.model_dump(exclude_defaults=True)


def render_search_filters(
    current_user: AppUser | None = None,
    search_filters: SearchFilters | None = None,
    result_count: int | None = None,
):
    if not search_filters:
        search_filters = SearchFilters()

    show_workspace_filter = bool(current_user and not current_user.is_anonymous)
    show_sort_option = (
        search_filters.search or search_filters.workflow or search_filters.workspace
    )
    with gui.div(className="row container-margin-reset", style={"fontSize": "0.9rem"}):
        if not show_sort_option:
            col_class = "col-12 col-md-7"
        elif show_workspace_filter:
            col_class = "col-9 col-md-7"
        else:
            col_class = "col-7"

        with gui.div(className=f"{col_class} d-flex align-items-center"):
            with gui.div(
                className="col-6 pe-1"
                if show_workspace_filter
                else "col-12 col-md-6 pe-md-1"
            ):
                search_filters.workflow = (
                    render_workflow_filter(value=search_filters.workflow) or ""
                )
            if show_workspace_filter:
                with gui.div(className="col-6 ps-1"):
                    search_filters.workspace = (
                        render_workspace_filter(
                            current_user=current_user,
                            value=search_filters.workspace,
                        )
                        or ""
                    )
            else:
                search_filters.workspace = ""

        if not show_sort_option:
            search_filters.sort = ""
        else:
            col_class = "col-3 col-md-5" if show_workspace_filter else "col-5"
            with gui.div(
                className=f"{col_class} d-flex gap-2 justify-content-end align-items-center",
            ):
                if result_count is not None:
                    gui.caption(
                        f"{result_count} {ngettext('result', 'results', result_count)}",
                        className="text-muted d-none d-md-block",
                    )
                with (
                    gui.styled(
                        """
                        @media(min-width: 768px) {
                            & .gui-input {
                                min-width: 170px;
                            }
                        }
                        @media(max-width: 767px) {
                            & div[class$="-control"] .hide-on-small-screens {
                                display: none !important;
                            }
                        }
                        """
                    ),
                    gui.div(),
                ):
                    sort_options = {
                        opt.name if opt != SortOptions.get() else None: (
                            opt.html_icon_label()
                        )
                        for opt in SortOptions
                    }
                    search_filters.sort = (
                        gui.selectbox(
                            label="",
                            options=sort_options,
                            key="search_sort",
                            value=search_filters.sort,
                            format_func=sort_options.__getitem__,
                            className="mb-0 text-nowrap",
                        )
                        or ""
                    )

    return search_filters


def render_search_bar_with_redirect(
    request: "Request",
    search_filters: SearchFilters,
    key: str = "global_search_query",
    id: str = "global_search_bar",
    max_width: str = "450px",
):
    from routers.root import explore_page

    search_query = render_search_bar(
        current_user=request.user,
        search_filters=search_filters,
        key=key,
        id=id,
        max_width=max_width,
    )
    if search_query != search_filters.search:
        search_filters.search = search_query
        raise gui.RedirectException(
            get_app_route_url(
                explore_page, query_params=search_filters.get_query_params()
            )
        )


def render_search_bar(
    current_user: AppUser | None,
    search_filters: SearchFilters,
    key: str,
    max_width: str,
    id: str | None = None,
    **props,
) -> str:
    id = id or f"--search_bar:{key}"

    with (
        gui.styled(
            rf"""
            & {{
                position: relative;
                max-width: {max_width};
                flex-grow: 1;
            }}
            & .gui-input {{
                margin: 0;
                width: 100%;
            }}
            & .clear_button {{
                position: absolute;
                top: 14px;
                right: 18px;
                font-size: 0.9em;
                margin: 0 !important;
            }}
            &::before {{
                content: "\f002";              /* FontAwesome glyph */
                font-family: "Font Awesome 7 Pro";
                position: absolute;
                top: 14px;
                left: 18px;
                pointer-events: none;          /* let clicks go through to the input */
                color: #888;
                font-size: 0.9em;
            }}
            """
        ),
        gui.div(),
    ):
        placeholder = get_placeholder_by_search_filters(
            search_filters=search_filters, current_user=current_user
        )
        search_query = gui.text_input(
            "",
            placeholder=placeholder,
            className="bg-light border-0 rounded-pill " + props.pop("className", ""),
            style=(
                dict(resize="none", paddingLeft="2.7rem", paddingRight="2.7rem")
                | props.pop("style", {})
            ),
            key=key,
            id=id,
            value=search_filters.search,
            autoComplete="off",
            **props,
        )

        # add a hidden submit button to allow form submission on pressing Enter
        gui.button(
            "",
            className="m-0 p-0",
            hidden=True,
            onClick=f"""
            event.preventDefault();
            document.getElementById("{id}").blur();
            """,
        )

        if search_query and gui.button(
            icons.cancel, type="link", className="clear_button"
        ):
            gui.session_state[key] = ""
            search_query = ""

    return search_query


def render_search_suggestions(search_filters: SearchFilters):
    from routers.root import explore_page

    with gui.div(
        className="pt-2 pb-1 overflow-auto overflow-sm-visible d-flex flex-nowrap flex-sm-wrap"
    ):
        for tag in Tag.get_options():
            url = get_app_route_url(
                explore_page,
                query_params=search_filters.model_copy(
                    update={"search": tag.name}
                ).get_query_params(),
            )
            render_pill_with_link(
                tag.render(),
                link_to=url,
                text_bg=None,
                className="me-2 my-1 bg-white border border-dark text-dark",
            )


def get_placeholder_by_search_filters(
    search_filters: SearchFilters,
    current_user: AppUser | None,
    fallback_workspace_text: str = "Gooey.AI",
) -> str:
    from daras_ai_v2.all_pages import page_slug_map, normalize_slug

    text = "Search"
    workspace = current_user and get_workspace_from_filter_value(
        current_user, search_filters.workspace
    )
    if workspace:
        if workspace.is_personal and workspace.created_by == current_user:
            workspace_text = "Personal Workspace"
        else:
            workspace_text = workspace.display_name(current_user=current_user)
        text += f": {workspace_text}"
    else:
        text += f" {fallback_workspace_text}"

    if search_filters.workflow:
        try:
            workflow_page = page_slug_map[normalize_slug(search_filters.workflow)]
        except KeyError:
            pass
        else:
            text += f" › {workflow_page.workflow.short_title}"

    return text


def render_workspace_filter(
    current_user: AppUser | None = None, key: str = "workspace_filter", value: str = ""
) -> str | None:
    if not current_user or current_user.is_anonymous:
        return None

    workspace_options = {
        get_filter_value_from_workspace(w): w.display_html(
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


def get_filter_value_from_workspace(workspace: "Workspace") -> str:
    return (workspace.handle_id and workspace.handle.name) or str(workspace.id)


def get_workspace_from_filter_value(
    user: AppUser, value: str
) -> typing.Optional["Workspace"]:
    if not value:
        return None

    for w in user.cached_workspaces:
        if str(w.id) == value or (w.handle_id and w.handle.name == value):
            return w

    return None


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


def render_search_results(
    qs: QuerySet[PublishedRun], user: AppUser | None, search_filters: SearchFilters
):
    qs = qs.prefetch_related("tags", "versions").select_related(
        "workspace", "last_edited_by", "saved_run"
    )

    def _render_run(pr: PublishedRun):
        show_workspace_author = not bool(search_filters and search_filters.workspace)
        is_member = bool(getattr(pr, "is_member", False))
        hide_last_editor = bool(pr.workspace_id and not is_member)
        show_run_count = is_member or search_filters.sort == SortOptions.most_runs.name

        render_saved_workflow_preview(
            pr,
            show_workflow_pill=True,
            show_workspace_author=show_workspace_author,
            show_run_count=show_run_count,
            hide_last_editor=hide_last_editor,
            hide_access_level=True,
            search_filters=search_filters,
        )

    grid_layout(1, qs, _render_run)


def get_filtered_published_runs(
    user: AppUser | None, search_filters: SearchFilters
) -> QuerySet:
    qs = PublishedRun.objects.all()
    qs = build_search_filter(qs, search_filters, user=user)
    qs = build_workflow_access_filter(qs, user)
    qs = build_sort_filter(qs, search_filters)
    return qs[:25]


def build_sort_filter(qs: QuerySet, search_filters: SearchFilters) -> QuerySet:
    match SortOptions.get(search_filters.sort):
        case SortOptions.featured:
            qs = qs.annotate(is_root_workflow=Q(published_run_id=""))
            fields = (
                "-is_approved_example",
                "-example_priority",
                "-is_root_workflow",
                F("is_created_by").desc(nulls_last=True),
                "-updated_at",
            )
            if search_filters.search:
                fields = ("-rank", *fields)
        case SortOptions.last_updated:
            fields = ("-updated_at",)
        case SortOptions.created_at:
            fields = ("-created_at",)
        case SortOptions.most_runs:
            fields = (
                "-run_count",
                F("is_created_by").desc(nulls_last=True),
                "-updated_at",
            )

    return qs.order_by(*fields).distinct(
        "id",
        *(get_field_from_ordering(f) for f in fields),
    )


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


def build_search_filter(
    qs: QuerySet, search_filters: SearchFilters, user: AppUser | None
) -> QuerySet:
    from daras_ai_v2.all_pages import page_slug_map, normalize_slug

    if user and search_filters.workspace:
        workspace = get_workspace_from_filter_value(user, search_filters.workspace)
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
        for word in search_filters.search.strip().split():
            for token in re.findall(SEARCH_TOKEN_ALLOWED_CHARS, word):
                tokens.append(token + ":*")
        raw_query = " & ".join(tokens)
        query = SearchQuery(raw_query, search_type="raw")

        vector = (
            SearchVector("title", weight="A")
            + SearchVector(
                "tags__name",
                "workspace__name",
                "workspace__handle__name",
                "created_by__display_name",
                weight="B",
            )
            + SearchVector("notes", weight="C")
        )
        qs = qs.annotate(search=vector, rank=SearchRank(vector, query))

        # filter on the search vector
        qs = qs.filter(search=query)

    return qs


def get_field_from_ordering(value: str | OrderBy) -> str:
    match value:
        case OrderBy():
            return value.expression.name
        case str():
            return value.lstrip("-")
        case _:
            raise ValueError(f"Invalid value: {value}")
