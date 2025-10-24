import typing
import gooey_gui as gui

from daras_ai_v2 import icons
from daras_ai_v2.fastapi_tricks import get_app_route_url
from widgets.saved_workflow import render_pill_with_link
from widgets.author import render_author_as_breadcrumb
from widgets.workflow_search import SearchFilters


if typing.TYPE_CHECKING:
    from app_users.models import AppUser
    from bots.models import PublishedRun, SavedRun, Workflow
    from daras_ai_v2.breadcrumbs import TitleBreadCrumbs
    from workspaces.models import Workspace


def render_header_title(tb: "TitleBreadCrumbs"):
    with (
        gui.styled("""
        & h1 { margin: 0 }
        @media (max-width: 768px) { & h1 { font-size: 1.5rem; line-height: 1.2 } }
        """),
        gui.div(className="container-margin-reset my-auto"),
    ):
        gui.write("# " + tb.title_with_prefix_url())


def render_help_button(workflow: "Workflow"):
    meta = workflow.get_or_create_metadata()
    if not meta.help_url:
        return

    with (
        gui.link(to=meta.help_url, target="_blank"),
        gui.tag(
            "button",
            type="button",
            className="btn btn-theme btn-tertiary m-0",
        ),
    ):
        gui.html(
            f'{icons.help_guide} <span class="text-muted d-none d-lg-inline">Help Guide</span>'
        )


def render_breadcrumbs_with_author(
    breadcrumbs: "TitleBreadCrumbs",
    *,
    pr: "PublishedRun",
    sr: "SavedRun",
    user: typing.Optional["AppUser"] = None,
    current_workspace: typing.Optional["Workspace"] = None,
):
    from routers.root import explore_page

    with gui.div(
        className="d-flex flex-wrap align-items-center container-margin-reset"
    ):
        if breadcrumbs.root_title:
            with gui.breadcrumbs(className="container-margin-reset me-2"):
                gui.breadcrumb_item(
                    breadcrumbs.root_title.title,
                    link_to=breadcrumbs.root_title.url,
                    className="text-muted",
                )

        is_root_example = pr.is_root() and pr.saved_run_id == sr.id
        if not is_root_example:
            with gui.div(className="d-flex align-items-center"):
                gui.write("by", className="me-2 d-none d-md-block text-muted")
                render_author_as_breadcrumb(
                    user=user, pr=pr, sr=sr, current_workspace=current_workspace
                )

        if pr.saved_run_id != sr.id:
            return

        for tag in pr.tags.all():
            query_params = SearchFilters(search=tag.name).get_query_params()
            render_pill_with_link(
                tag.render(),
                link_to=get_app_route_url(explore_page, query_params=query_params),
                className="ms-2 border",
            )
