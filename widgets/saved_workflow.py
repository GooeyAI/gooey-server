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


def render_saved_workflow_preview(
    page_cls: typing.Union["BasePage", typing.Type["BasePage"]],
    published_run: PublishedRun,
    show_workspace_author: bool = False,
    workflow_pill: str | None = None,
    hide_visibility_pill: bool = False,
    hide_version_notes: bool = False,
    hide_last_editor: bool = False,
    hide_updated_at: bool = False,
    show_all_run_counts: bool = False,
):
    tb = get_title_breadcrumbs(page_cls, published_run.saved_run, published_run)

    output_url = (
        page_cls.preview_image(published_run.saved_run.state) or published_run.photo_url
    )

    with gui.div(className="py-1 row"):
        with (
            gui.styled(
                """
                & h4, & h1, & p {
                    margin: 0 !important;
                }
                @media (max-width: 768px) {
                    & .saved-workflow-notes span {
                        font-size: 0.9rem;
                        -webkit-line-clamp: 3 !important;
                    }
                }
                """
            ),
            gui.div(
                className="order-last order-md-first d-flex flex-column gap-md-2"
                + (" col-md-10" if output_url else "")
            ),
        ):
            with gui.div(className="d-flex align-items-center"):
                with gui.link(to=published_run.get_app_url()):
                    gui.write(f"#### {truncate_text_words(tb.h1_title, 80)}")
                render_title_pills(published_run, workflow_pill)

            with gui.div(className="row"):
                with gui.div(
                    className="saved-workflow-notes mb-2 mb-md-0"
                    + ("" if output_url else " col-10")
                ):
                    if published_run.notes:
                        gui.caption(
                            published_run.notes, line_clamp=2, lineClampExpand=False
                        )
                if not output_url:
                    with gui.div(className="col-2 text-center m-auto"):
                        workflow = Workflow(published_run.workflow)
                        metadata = workflow.get_or_create_metadata()
                        gui.write(f"# {metadata.emoji}")

            render_footer_breadcrumbs(
                published_run=published_run,
                show_workspace_author=show_workspace_author,
                hide_version_notes=hide_version_notes,
                hide_visibility_pill=hide_visibility_pill,
                hide_last_editor=hide_last_editor,
                hide_updated_at=hide_updated_at,
                show_all_run_counts=show_all_run_counts,
            )

        if output_url:
            render_workflow_media(output_url, published_run)


def render_title_pills(published_run: PublishedRun, workflow_pill: str | None):
    with gui.div(
        className="d-md-flex d-none align-items-center ms-2",
        style={"font-size": "0.9rem"},
    ):
        if workflow_pill:
            gui.pill(
                workflow_pill,
                unsafe_allow_html=True,
                className="border border-dark ms-2",
            )

        for _, platform_id in get_demo_bots(published_run):
            platform = Platform(platform_id)
            label = f"{platform.get_icon()} {platform.get_title()}"
            bg_color = platform.get_demo_button_color()
            if bg_color:
                style = dict(
                    backgroundColor=bg_color,
                    borderColor=bg_color + " !important",
                    color="white",
                )
            else:
                style = dict(
                    backgroundColor="#f8f9fa",
                    color="black",
                )
            with gui.tag(
                "span",
                className="badge rounded-pill border ms-2",
                style=style,
            ):
                gui.html(label)


FOOTER_CSS = """
& {
    font-size: 0.9rem;
    white-space: nowrap;
}
& .author-name {
    max-width: 200px; 
    overflow: hidden; 
    text-overflow: ellipsis; 
}
& .workspace-icon {
    margin: 0 0.17rem;
}
& i[class^="fa"] {
    width: 20px;
    margin: 0 2px;
    text-align: center;
}
& > div {
    margin-right: 0.75rem;
    display: flex;
    align-items: center;
}
@media (max-width: 768px) {
    & {
        display: grid !important;
        grid-template-areas: 
            "workspace author"
            "notes notes"
            "time runs";
        gap: 0.25rem 0.75rem;
        align-items: start;
        white-space: normal;
    }
    & .workspace-container {
        grid-area: workspace;
    }
    & .author-container {
        grid-area: author;
    }
    & .notes-container {
        grid-area: notes;
    }
    & .time-container {
        grid-area: time;
    }
    & .runs-container {
        grid-area: runs;
    }
    & > div {
        margin: 0;
    }
}
"""


def render_footer_breadcrumbs(
    published_run: PublishedRun,
    show_workspace_author: bool,
    hide_visibility_pill: bool,
    hide_version_notes: bool,
    hide_last_editor: bool,
    hide_updated_at: bool,
    show_all_run_counts: bool = False,
):
    latest_version = published_run.versions.latest()

    with (
        gui.styled(FOOTER_CSS),
        gui.div(
            className="flex-grow-1 d-flex align-items-end flex-wrap flex-lg-nowrap"
        ),
    ):
        if published_run.workspace.is_personal:
            show_workspace_author = False
        if show_workspace_author:
            # don't repeat author for personal workspaces
            with gui.div(className="d-flex align-items-center workspace-container"):
                render_author_from_workspace(
                    published_run.workspace,
                    image_size="24px",
                    responsive=False,
                )

        if not hide_last_editor and published_run.last_edited_by:
            with gui.div(
                className="d-flex align-items-center text-truncate author-container"
            ):
                render_author_from_user(
                    published_run.last_edited_by,
                    image_size="24px",
                    responsive=False,
                )

        if not hide_version_notes and latest_version and latest_version.change_notes:
            with gui.div(
                className="text-truncate text-muted d-flex align-items-center notes-container",
                style={"maxWidth": "250px"},
            ):
                gui.html(f"{icons.notes} {html.escape(latest_version.change_notes)}")

        updated_at = published_run.saved_run.updated_at
        if (
            updated_at
            and isinstance(updated_at, datetime.datetime)
            and not hide_updated_at
        ):
            with gui.div(className="d-flex align-items-center time-container"):
                gui.write(
                    f"{icons.time} {get_relative_time(updated_at)}",
                    unsafe_allow_html=True,
                    className="text-muted",
                )

        if published_run.run_count >= 50 or show_all_run_counts:
            run_count = format_number_with_suffix(published_run.run_count)
            with gui.div(className="d-flex align-items-center runs-container"):
                gui.write(
                    f"{icons.run} {run_count} runs",
                    unsafe_allow_html=True,
                    className="text-muted text-nowrap",
                )

        if not hide_visibility_pill:
            gui.caption(
                published_run.get_share_badge_html(),
                unsafe_allow_html=True,
            )


def render_workflow_media(output_url: str, published_run: PublishedRun):
    with (
        gui.styled(
            """
            & img, & video, & object {
                width: 100%; 
                height: auto;
                max-height: 30vh;
                margin: 0;
                object-fit: cover;
                border-radius: 12px;
                pointer-events: none !important;
            }
            """
        ),
        gui.div(
            className="col-md-2 order-first order-md-last text-center mb-2 mb-md-0",
        ),
        gui.link(to=published_run.get_app_url()),
    ):
        input_url = published_run.saved_run.state.get("input_image")
        if input_url:
            col1, col2 = gui.columns(2, className="row g-2", responsive=False)
            with col1:
                gui.image(input_url)
            with col2:
                placeholder = gui.dummy()
        else:
            placeholder = gui.dummy()

    if not output_url:
        return
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
