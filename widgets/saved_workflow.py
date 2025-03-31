from __future__ import annotations

import datetime
import typing

import gooey_gui as gui
from furl import furl

from bots.models import PublishedRun, PublishedRunPermission, Workflow
from daras_ai.image_input import truncate_text_words
from daras_ai.text_format import format_number_with_suffix
from daras_ai_v2 import icons
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs
from daras_ai_v2.meta_preview_url import meta_preview_url
from daras_ai_v2.utils import get_relative_time
from widgets.author import render_author_from_workspace, render_author_from_user

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
}

@media (min-width: 768px) {
    & .gui_example_media{
        width: 130px;
    }
}

& .render_example_author_meta > a {
    text-decoration: none !important;
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
    version = published_run.versions.latest()
    output_url = (
        page_cls.preview_image(published_run.saved_run.state) or published_run.photo_url
    )

    with gui.div(className="position-relative py-2 pe-0"):
        with (
            gui.styled(WORKFLOW_PREVIEW_STYLE),
            gui.div(className=f"position-relative overflow-hidden"),
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
                                if not hide_visibility_pill:
                                    gui.pill(
                                        published_run.get_share_badge_html(),
                                        unsafe_allow_html=True,
                                        className="border border-dark",
                                    )
                                if workflow_pill:
                                    gui.pill(
                                        workflow_pill,
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
                    with gui.div(
                        className="d-none d-md-flex flex-1 align-items-center render_example_author_meta"
                    ):
                        render_saved_workflow_author(
                            published_run=published_run,
                            show_workspace_author=show_workspace_author,
                        )
                        if not hide_version_notes:
                            with gui.div(
                                className="container-margin-reset mt-2 mt-md-0 d-flex gap-2 ms-2 align-items-center"
                            ):
                                if version.change_notes:
                                    gui.write(" • ")
                                    gui.caption(
                                        f"{icons.notes} {version.change_notes}",
                                        unsafe_allow_html=True,
                                        style={"fontSize": "0.9rem"},
                                        line_clamp=1,
                                        lineClampExpand=False,
                                    )
                with (
                    gui.div(
                        className=f"flex-grow-1 {'d-none d-md-flex' if output_url else 'd-flex'} justify-content-end ms-2"
                    ),
                    gui.div(
                        className="gui_example_media d-flex align-items-center justify-content-center",
                    ),
                    gui.link(
                        to=published_run.get_app_url(),
                        className="d-flex",
                    ),
                ):
                    render_saved_workflow_output(output_url, published_run)

        with gui.div(className="d-md-none mt-2"):
            render_saved_workflow_author(
                published_run=published_run,
                show_workspace_author=show_workspace_author,
            )
            if not hide_version_notes:
                with gui.div(className="container-margin-reset mt-2 mt-md-0"):
                    if version.change_notes:
                        gui.caption(
                            f"{icons.notes} {version.change_notes}",
                            unsafe_allow_html=True,
                            style={"fontSize": "0.9rem"},
                            line_clamp=1,
                        )


def render_saved_workflow_author(
    published_run: PublishedRun, show_workspace_author: bool = True
):
    updated_at = published_run.saved_run.updated_at or ""
    with gui.div(
        className="d-flex gap-2 align-items-center container-margin-reset render_example_author_meta",
    ):
        if show_workspace_author:
            render_author_from_workspace(
                published_run.workspace,
                image_size="24px",
                text_size="0.9rem",
                responsive=False,
            )
        else:
            render_author_from_user(
                published_run.last_edited_by,
                image_size="24px",
                text_size="0.9rem",
                responsive=False,
            )

        if published_run.visibility == PublishedRunPermission.CAN_FIND:
            run_icon = '<i class="fa-regular fa-person-running"></i>'
            count = published_run.get_run_count()
            if count > 0:
                run_count = format_number_with_suffix(count)
                gui.write(" • ")
                gui.caption(
                    f"{run_icon} {run_count} runs",
                    unsafe_allow_html=True,
                    style={"fontSize": "0.9rem"},
                    className="text-dark",
                )

        if published_run.last_edited_by:
            gui.write(" • ")

        if updated_at and isinstance(updated_at, datetime.datetime):
            gui.caption(
                f"{get_relative_time(updated_at)}",
                style={"fontSize": "0.9rem"},
                className="container-margin-reset",
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
