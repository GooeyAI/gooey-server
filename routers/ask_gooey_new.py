import fastapi
from django.utils.text import slugify
from furl import furl
from starlette.requests import Request

import gooey_gui as gui
from bots.models import SavedRun
from daras_ai.image_input import truncate_text_words
from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_route_path
from daras_ai_v2.gooey_builder import (
    can_launch_gooey_builder,
    render_standalone_gooey_builder,
)
from daras_ai_v2.meta_content import raw_build_meta_tags
from routers.base_auth import get_login_url
from routers.custom_api_router import CustomAPIRouter
from routers.root import get_og_url_path, sidebar_page_wrapper
from workspaces.models import Workspace

META_TITLE = "Explore | Gooey.AI"
META_DESCRIPTION = "Find, fork and run your field’s favorite AI recipes on Gooey.AI"

app = CustomAPIRouter()


@gui.route(app, "/new/")
def ask_gooey_new_page(request: Request):
    if not request.user or request.user.is_anonymous:
        raise gui.RedirectException(get_login_url(request))

    with sidebar_page_wrapper(request, full_width_content=True):
        render_ask_gooey_new(request=request, workspace=None)

    return {
        "meta": build_meta_tags(url=get_og_url_path(request)),
    }


@gui.route(app, "/new/{title}-{run_id}/")
def gooey_builder_run_route(request: Request, title: str, run_id: str):
    """Renders only the gooey builder chat for a builder prompt run, without
    the associated workflow. Redirects to the child workflow whenever the
    builder updates it."""
    if not request.user or request.user.is_anonymous:
        raise gui.RedirectException(get_login_url(request))

    try:
        builder_sr = SavedRun.objects.get(
            run_id=run_id, surface=SavedRun.Surface.builder_prompt
        )
    except SavedRun.DoesNotExist:
        raise fastapi.HTTPException(status_code=404)
    if builder_sr.uid != request.user.uid and not request.user.is_admin():
        raise fastapi.HTTPException(status_code=404)

    # the builder embed sets this flag on "new conversation"; the standalone
    # page is tied to one builder run, so start fresh from the hero page
    if gui.session_state.pop("builderOnNewConversation", None):
        raise gui.RedirectException(get_route_path(ask_gooey_new_page))

    # explicit viewport height so the embed's h-100 fills the screen
    with (
        sidebar_page_wrapper(request, full_width_content=True),
        gui.div(
            className="w-100 d-flex flex-column",
            style={"height": "100dvh"},
        ),
    ):
        render_standalone_gooey_builder(
            event_key="gooey-builder",
            request=request,
            builder_sr=builder_sr,
        )

    return {
        "meta": build_meta_tags(url=get_og_url_path(request)),
    }


def get_gooey_builder_run_url(builder_sr: SavedRun) -> str:
    slug = (
        slugify(
            truncate_text_words(builder_sr.state.get("input_prompt") or "", maxlen=40)
        )
        or "untitled"
    )
    return str(
        furl(settings.APP_BASE_URL)
        / get_route_path(
            gooey_builder_run_route, dict(title=slug, run_id=builder_sr.run_id)
        )
    )


def build_meta_tags(url: str):
    return raw_build_meta_tags(
        url=url,
        title=META_TITLE,
        description=META_DESCRIPTION,
    )


def render_ask_gooey_new(
    request: fastapi.Request,
    workspace: Workspace | None,
    title: str = "What will you build today?",
    highlight: str = "",
    placeholder: str = "Build an agent for farmers in Kenya",
):
    """Centered "What can I help with?" hero prompt for /explore.

    On submit it starts a builder-only conversation (no workflow attached) and
    the React component navigates the user to the standalone builder page at
    ``/new/<title>-<run_id>/``.
    """
    if not can_launch_gooey_builder(request, workspace):
        return
    gui.component(
        "AskGooeyNew",
        title=title,
        highlight=highlight,
        placeholder=placeholder,
    )
