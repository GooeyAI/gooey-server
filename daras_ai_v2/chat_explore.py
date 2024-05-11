import datetime

import gooey_ui as st
from bots.models import BotIntegration, Platform, PublishedRunVisibility, Message
from daras_ai.text_format import format_number_with_suffix
from daras_ai_v2 import icons
from daras_ai_v2.bot_integration_widgets import get_bot_test_link
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.user_date_widgets import render_local_dt_attrs
from recipes.VideoBots import VideoBotsPage


def render():
    st.write("# Explore our Bots")
    st.caption("Tap on a bot to chat with it.")

    st.newline()

    integrations = BotIntegration.objects.filter(
        published_run__isnull=False,
        published_run__visibility=PublishedRunVisibility.PUBLIC,
        published_run__is_approved_example=True,
    ).exclude(published_run__published_run_id="")

    grid_layout(3, integrations, _render_bi)


def _render_bi(bi: BotIntegration):
    st.html(
        f"""
        <h4>
            {Platform(bi.platform).get_icon()} 
            &nbsp; 
            <a href="{get_bot_test_link(bi)}">{bi.name}</a>
        </h4>
        """,
        unsafe_allow_html=True,
    )

    if bi.published_run.created_by:
        with st.div(className="mb-1 text-truncate", style={"height": "1.5rem"}):
            VideoBotsPage.render_author(
                bi.published_run.created_by,
                image_size="20px",
                text_size="0.9rem",
            )

    tb = get_title_breadcrumbs(
        VideoBotsPage, bi.published_run.saved_run, bi.published_run
    )
    st.write(tb.h1_title)

    with st.div(className="d-flex align-items-center justify-content-between"):
        with st.div():
            updated_at = bi.published_run.saved_run.updated_at
            if updated_at and isinstance(updated_at, datetime.datetime):
                st.caption("Loading...", **render_local_dt_attrs(updated_at))

        num_msgs = Message.objects.filter(conversation__bot_integration=bi).count()
        if num_msgs:
            msg_count = format_number_with_suffix(num_msgs)
            st.caption(f"{icons.chat} {msg_count} Msgs", unsafe_allow_html=True)
        else:
            st.caption("&nbsp;", unsafe_allow_html=True)

    if bi.published_run.notes:
        st.caption(bi.published_run.notes, line_clamp=2)
