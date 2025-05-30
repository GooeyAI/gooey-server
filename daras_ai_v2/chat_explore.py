import datetime

import gooey_gui as gui

from bots.models import BotIntegration, Message, Platform, PublishedRun
from bots.models.workflow import WorkflowAccessLevel
from daras_ai.text_format import format_number_with_suffix
from daras_ai_v2 import icons
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.user_date_widgets import render_local_dt_attrs
from recipes.VideoBots import VideoBotsPage
from widgets.author import render_author_from_user


def render():
    gui.write("# Explore our Bots")
    gui.caption("Tap on a bot to chat with it.")

    gui.newline()

    integrations = BotIntegration.objects.filter(
        published_run__in=PublishedRun.objects.filter(
            PublishedRun.approved_example_q()
        ),
        public_visibility__gt=WorkflowAccessLevel.VIEW_ONLY,
    )
    grid_layout(3, integrations, _render_bi)


def _render_bi(bi: BotIntegration):
    gui.html(
        f"""
        <h4>
            {Platform(bi.platform).get_icon()} 
            &nbsp; 
            <a href="{bi.get_bot_test_link()}">{bi.name}</a>
        </h4>
        """,
    )

    if bi.published_run.created_by:
        with (
            gui.div(className="mb-1 text-truncate", style={"height": "1.5rem"}),
            gui.styled("& .author-name { font-size: 0.9rem; }"),
        ):
            render_author_from_user(bi.published_run.created_by, image_size="20px")

    tb = get_title_breadcrumbs(
        VideoBotsPage, bi.published_run.saved_run, bi.published_run
    )
    with gui.link(to=bi.published_run.get_app_url()):
        gui.write(tb.h1_title, className="container-margin-reset")

    with gui.div(className="d-flex align-items-center justify-content-between"):
        with gui.div():
            updated_at = bi.published_run.saved_run.updated_at
            if updated_at and isinstance(updated_at, datetime.datetime):
                gui.caption("Loading...", **render_local_dt_attrs(updated_at))

        num_msgs = Message.objects.filter(conversation__bot_integration=bi).count()
        if num_msgs:
            msg_count = format_number_with_suffix(num_msgs)
            gui.caption(f"{icons.chat} {msg_count} Msgs", unsafe_allow_html=True)
        else:
            gui.caption("&nbsp;", unsafe_allow_html=True)

    if bi.published_run.notes:
        gui.caption(bi.published_run.notes, line_clamp=2)
