from __future__ import annotations

import datetime
import html
import typing

import gooey_gui as gui
from furl import furl

from bots.models import PublishedRun, Workflow, Platform
from daras_ai.image_input import truncate_text_words
from daras_ai.text_format import format_number_with_suffix
from daras_ai_v2 import icons
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs
from daras_ai_v2.meta_preview_url import meta_preview_url
from daras_ai_v2.utils import get_relative_time
from widgets.author import render_author_from_workspace, render_author_from_user
from widgets.demo_button import get_demo_bots

if typing.TYPE_CHECKING:
    from daras_ai_v2.base import BasePage

WORKFLOW_PREVIEW_STYLE = """
& h4, & h1, & p {
    margin: 0 !important;
}

& .gui_example_media > a {
    text-decoration: none !important;
}

& .gui_example_media > a > img {
    pointer-events: none !important;
}

& .gui_example_media {
    width: 100%;
    min-width: 100px;
}

& .gui_example_media img, & .gui_example_media video, & .gui_example_media object {
    max-width: 100%; 
    height: 100%;
    margin: 0;
    object-fit: cover;
    border-radius: 12px;
}

@media (min-width: 768px) {
    & .gui_example_media{
        width: 130px;
    }

    & .w-md-auto {
        width: auto !important;
    }
}
"""

SEPARATOR_CSS = """
& > :not(.sep-hide):not(:empty):not(:last-child)::after {
  content: "•";
  margin: 0 0.5rem;
  color: black;
  display: inline-block;
  vertical-align: middle;
}

@media (min-width: 768px) {
    & > .sep-md-show:not(:empty):not(:last-child)::after {
      content: "•";
      margin: 0 0.5rem;
      color: black;
      display: inline-block;
      vertical-align: middle;
    }
}
"""


def render_saved_workflow_preview(
    page_cls: typing.Union["BasePage", typing.Type["BasePage"]],
    published_run: PublishedRun,
    show_workspace_author: bool = False,
    workflow_pill: str | None = None,
    hide_visibility_pill: bool = False,
    hide_version_notes: bool = False,
):
    tb = get_title_breadcrumbs(page_cls, published_run.saved_run, published_run)
    output_url = (
        page_cls.preview_image(published_run.saved_run.state) or published_run.photo_url
    )
    demo_bots = get_demo_bots(published_run)
    with gui.div(className="position-relative py-2 pe-0"):
        with (
            gui.styled(WORKFLOW_PREVIEW_STYLE),
            gui.div(className="position-relative overflow-hidden"),
            gui.div(className="d-flex flex-column gap-2"),
        ):
            if output_url:
                with (
                    gui.div(className="flex-grow-1 d-md-none"),
                    gui.div(
                        className="flex-grow-1 position-relative d-flex justify-content-center"
                    ),
                    gui.link(to=published_run.get_app_url()),
                    gui.div(className="gui_example_media"),
                ):
                    render_saved_workflow_output(output_url, published_run)
            with gui.div(className="d-flex align-items-stretch"):
                with gui.div(className="flex-grow-1 d-flex flex-column gap-md-2"):
                    with gui.div(className="flex-grow-1 d-flex flex-column gap-md-2"):
                        with gui.div(className="d-flex align-items-center"):
                            with gui.div(), gui.link(to=published_run.get_app_url()):
                                gui.write(
                                    f"#### {truncate_text_words(tb.h1_title, 80)}"
                                )
                            with gui.div(
                                className="d-md-flex d-none align-items-center ms-2 mt-1",
                                style={"font-size": "0.9rem"},
                            ):
                                if workflow_pill:
                                    gui.pill(
                                        workflow_pill,
                                        unsafe_allow_html=True,
                                        className="border border-dark ms-2",
                                    )

                                for _, platform_id in demo_bots:
                                    platform = Platform(platform_id)
                                    label = (
                                        f"{platform.get_icon()} {platform.get_title()}"
                                    )
                                    gui.pill(
                                        label,
                                        unsafe_allow_html=True,
                                        className="border border-dark ms-2",
                                    )
                        if published_run.notes:
                            with gui.div(className="d-none d-md-block pe-5"):
                                gui.caption(
                                    published_run.notes,
                                    line_clamp=3,
                                    lineClampExpand=False,
                                )
                            with gui.div(className="d-md-none"):
                                gui.caption(
                                    published_run.notes,
                                    line_clamp=2,
                                    lineClampExpand=False,
                                    style={"fontSize": "0.9rem"},
                                )
                    with gui.div(className="d-none d-md-block"):
                        render_preview_footer(
                            published_run=published_run,
                            show_workspace_author=show_workspace_author,
                            hide_version_notes=hide_version_notes,
                            hide_visibility_pill=hide_visibility_pill,
                        )
                with (
                    gui.div(
                        className=f"flex-grow-1 {'d-none d-md-flex' if output_url else 'd-flex'} justify-content-end ms-2"
                    ),
                    gui.div(
                        className="gui_example_media d-flex align-items-center justify-content-center",
                    ),
                    gui.link(to=published_run.get_app_url(), className="d-flex"),
                ):
                    render_saved_workflow_output(output_url, published_run)

            with gui.div(className="d-md-none"):
                render_preview_footer(
                    published_run,
                    show_workspace_author=show_workspace_author,
                    hide_version_notes=hide_version_notes,
                    hide_visibility_pill=hide_visibility_pill,
                )


def render_preview_footer(
    published_run: PublishedRun,
    show_workspace_author: bool,
    hide_visibility_pill: bool,
    hide_version_notes: bool,
):
    latest_version = published_run.versions.latest()

    with (
        gui.styled(SEPARATOR_CSS),
        gui.div(
            className="d-flex align-items-center flex-wrap flex-lg-nowrap",
            style={"fontSize": "0.9rem"},
        ),
    ):
        if not hide_version_notes and latest_version and latest_version.change_notes:
            with gui.div(
                className="d-flex align-items-center w-100 w-md-auto sep-hide sep-md-show"
            ):
                render_change_notes(latest_version.change_notes)

        if show_workspace_author and not published_run.workspace.is_personal:
            # don't repeat author for personal workspaces
            with gui.div(className="d-flex align-items-center"):
                render_author_from_workspace(
                    published_run.workspace,
                    image_size="24px",
                    responsive=False,
                    name_style={
                        "maxWidth": "100px",
                        "overflow": "hidden",
                        "textOverflow": "ellipsis",
                    },
                )

        if published_run.last_edited_by:
            with gui.div(className="d-flex align-items-center text-truncate"):
                render_author_from_user(
                    published_run.last_edited_by,
                    image_size="24px",
                    responsive=False,
                    name_style={
                        "maxWidth": "100px",
                        "overflow": "hidden",
                        "textOverflow": "ellipsis",
                    },
                )

        render_last_updated_at(published_run)

        render_run_count(published_run)

        if not hide_visibility_pill:
            gui.caption(
                published_run.get_share_badge_html(),
                unsafe_allow_html=True,
                style={"whiteSpace": "nowrap"},
            )


def render_author_run_count_row(
    published_run: PublishedRun, show_workspace_author: bool = True
):
    with (
        gui.styled(SEPARATOR_CSS),
        gui.div(
            className="d-flex align-items-center container-margin-reset gap-2 flex-wrap",
            style={"fontSize": "0.9rem"},
        ),
    ):
        if show_workspace_author:
            render_author_from_workspace(
                published_run.workspace, image_size="24px", responsive=False
            )

        if published_run.last_edited_by and not (
            # don't repeat author for personal workspaces
            show_workspace_author and published_run.workspace.is_personal
        ):
            with gui.div(style=dict(display="contents")):
                render_author_from_user(
                    published_run.last_edited_by, image_size="24px", responsive=False
                )

        render_run_count(published_run)


def render_change_notes_visibility_row(
    published_run: PublishedRun,
    hide_version_notes: bool = False,
    hide_visibility_pill: bool = False,
):
    with (
        gui.styled(SEPARATOR_CSS),
        gui.div(className="d-flex align-items-center container-margin-reset gap-2"),
    ):
        if not hide_version_notes:
            render_change_notes(published_run)

        if not hide_visibility_pill:
            gui.caption(
                published_run.get_share_badge_html(),
                unsafe_allow_html=True,
                style={"whiteSpace": "nowrap"},
            )


def render_change_notes(change_notes: str):
    gui.caption(
        f"{icons.notes} {html.escape(change_notes)}",
        unsafe_allow_html=True,
        line_clamp=1,
        lineClampExpand=False,
    )


def render_last_updated_at(published_run: PublishedRun):
    updated_at = published_run.saved_run.updated_at
    if updated_at and isinstance(updated_at, datetime.datetime):
        gui.write(
            f"{icons.clock} {get_relative_time(updated_at)}",
            className="text-nowrap",
            unsafe_allow_html=True,
        )


def render_run_count(published_run: PublishedRun):
    if published_run.run_count > 1:
        run_count = format_number_with_suffix(published_run.run_count)
        gui.write(
            f"{icons.run} {run_count} runs",
            unsafe_allow_html=True,
            className="text-dark text-nowrap",
        )


def render_saved_workflow_output(output_url: str, published_run: PublishedRun):
    state = published_run.saved_run.state
    if not output_url:
        workflow = Workflow(published_run.workflow)
        metadata = workflow.get_or_create_metadata()
        gui.write(f"# {metadata.emoji}", className="m-0 container-margin-reset")
        return

    input_url = state.get("input_image")
    if input_url:
        col1, col2 = gui.columns(2, className="row g-2", responsive=False)
        with col1:
            gui.image(input_url)
        with col2:
            placeholder = gui.dummy()
    else:
        placeholder = gui.dummy()

    with placeholder:
        preview_url, is_video = meta_preview_url(output_url)
        if is_video:
            output_url = furl(output_url).add(fragment_args={"t": "0.001"}).url
            gui.html(
                f"""
                <object data={preview_url!r} class="gui-video">
                  <video src={output_url!r} class="gui-video" autoplay playsInline loop muted>
                </object>
                """
            )
        else:
            gui.html(
                f"""
                <object data={preview_url!r} class="gui-image">
                  <img src={output_url!r} class="gui-image" autoplay playsInline loop muted>
                </object>
                """
            )
