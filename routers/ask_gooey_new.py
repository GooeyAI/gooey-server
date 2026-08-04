import fastapi
import gooey_gui as gui
from starlette.requests import Request

from bots.models import PublishedRun
from daras_ai_v2 import settings
from daras_ai_v2.gooey_builder import can_launch_gooey_builder
from daras_ai_v2.meta_content import raw_build_meta_tags
from routers.custom_api_router import CustomAPIRouter
from routers.root import get_og_url_path, page_wrapper
from workspaces.models import Workspace

META_TITLE = "Explore | Gooey.AI"
META_DESCRIPTION = "Find, fork and run your field’s favorite AI recipes on Gooey.AI"

app = CustomAPIRouter()


@gui.route(app, "/new/")
@gui.route(app, "/explore2/")
def ask_gooey_new_page(request: Request):
    with page_wrapper(request, show_search_bar=False):
        render_ask_gooey_new(request=request, workspace=None)

    return {
        "meta": build_meta_tags(url=get_og_url_path(request)),
    }


def build_meta_tags(url: str):
    return raw_build_meta_tags(
        url=url,
        title=META_TITLE,
        description=META_DESCRIPTION,
    )


def render_ask_gooey_new(
    request: fastapi.Request,
    workspace: Workspace | None,
    title: str = "What do you want to build today?",
    highlight: str = "build",
    placeholder: str = "India stock market today",
):
    """Centered "What can I help with?" hero prompt for /explore.

    On submit it calls ``gooey_builder_on_send_message`` and the React
    component navigates the user to the newly-created workflow run.
    """
    if not can_launch_gooey_builder(request, workspace):
        return
    if not settings.BOT_GENERATOR_EXAMPLE_ID:
        return

    from recipes.VideoBots import VideoBotsPage

    try:
        bot_generator_pr = VideoBotsPage.get_pr_from_example_id(
            example_id=settings.BOT_GENERATOR_EXAMPLE_ID
        )
    except PublishedRun.DoesNotExist:
        return
    gui.component(
        "AskGooeyNew",
        workflow_url=bot_generator_pr.get_app_url(),
        title=title,
        highlight=highlight,
        placeholder=placeholder,
    )
