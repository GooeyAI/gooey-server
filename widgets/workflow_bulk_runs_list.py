from functools import partial

import gooey_gui as gui

from app_users.models import AppUser
from bots.models.published_run import PublishedRun, PublishedRunVersion
from bots.models.saved_run import SavedRun
from daras_ai_v2 import breadcrumbs, icons
from daras_ai_v2.field_render import field_desc, field_title
from daras_ai_v2.workflow_url_input import workflow_url_input
from recipes.BulkRunner import list_view_editor
from workspaces.models import Workspace


def render_workflow_bulk_runs_list(
    *,
    key: str = "bulk_runs",
    user: AppUser | None,
    workspace: Workspace | None,
    sr: SavedRun,
    pr: PublishedRun,
    default_url: str = "https://gooey.ai/bulk/copilot-evaluator-g179r9bdulc1/",
):
    from recipes.VideoBots import VideoBotsPage

    gui.session_state.setdefault(key, [default_url])

    with gui.div(className="d-flex align-items-center gap-2"):
        gui.write(
            "##### " + field_title(VideoBotsPage.RequestModel, key),
            help=field_desc(VideoBotsPage.RequestModel, key),
        )
        if gui.button(
            f"{icons.add} Add",
            type="tertiary",
            className="p-1 mb-2",
            key=f"add_{key}",
        ):
            gui.session_state.setdefault(f"--list-view:{key}", []).append(
                {"url": default_url}
            )

    bulk_runs = []
    list_view_editor(
        key=key,
        render_inputs=partial(render_inputs, bulk_runs=bulk_runs, user=user),
        flatten_dict_key="url",
    )
    submit_evaluation_button(
        user=user, workspace=workspace, key=key, bulk_runs=bulk_runs, sr=sr, pr=pr
    )


def render_inputs(
    key: str,
    del_key: str,
    d: dict,
    *,
    bulk_runs: list[dict],
    user: AppUser | None,
):
    from recipes.BulkRunner import BulkRunnerPage

    ret = workflow_url_input(
        page_cls=BulkRunnerPage,
        key=key,
        internal_state=d,
        del_key=del_key,
        current_user=user,
    )
    if not ret:
        return
    page_cls, sr, pr = ret
    if pr and pr.saved_run_id == sr.id:
        bulk_runs.append(dict(saved_run=None, published_run=pr))
    else:
        bulk_runs.append(dict(saved_run=sr, published_run=None))


def submit_evaluation_button(
    *,
    user: AppUser | None,
    workspace: Workspace | None,
    key: str,
    bulk_runs: list[dict],
    sr: SavedRun,
    pr: PublishedRun,
):
    if not (bulk_runs and user and workspace):
        return

    success_alert = gui.use_alert_dialog(key=f"{key}_evaluation_success")

    with gui.div(className="d-flex align-items-center gap-2"):
        with gui.tooltip("Evaluate this run against your last Saved version."):
            pressed_submit = gui.button(
                "<i class='fa fa-code-compare'></i> Run Evaluation",
                className="p-2 ms-0",
                key=f"run_evaluation_{key}",
            )
            if pressed_submit:
                on_submit(
                    success_alert=success_alert,
                    bulk_runs=bulk_runs,
                    user=user,
                    workspace=workspace,
                    sr=sr,
                    pr=pr,
                )

    bulk_run_urls = gui.session_state.get("_bulk_run_urls")
    if success_alert.is_open and bulk_run_urls:
        render_success_alert(success_alert, bulk_run_urls)
    else:
        gui.session_state.pop("_bulk_run_urls", None)


def on_submit(
    *,
    success_alert: gui.AlertDialogRef,
    bulk_runs: list[dict],
    user: AppUser,
    workspace: Workspace,
    sr: SavedRun,
    pr: PublishedRun,
):
    from recipes.BulkRunner import BulkRunnerPage

    if pr and pr.saved_run_id != sr.id:
        # published run is not the same as the current run, so we can compare the two directly
        v1_url = pr.get_app_url()
        v2_url = sr.get_app_url()
    else:
        # retrieve the previous version from history to compare with the current published run
        try:
            prev_version = pr.versions.exclude(saved_run=sr).latest()
            v1_url = prev_version.saved_run.get_app_url()
        except PublishedRunVersion.DoesNotExist:
            gui.error("No previous version found :(")
            return
        v2_url = sr.get_app_url()

    success_alert.set_open(True)
    gui.session_state["_bulk_run_urls"] = bulk_run_urls = []

    for run_dict in bulk_runs:
        bulk_run: PublishedRun | SavedRun = (
            run_dict["published_run"] or run_dict["saved_run"]
        )
        result, new_sr = bulk_run.submit_api_call(
            workspace=workspace,
            request_body=dict(run_urls=[v1_url, v2_url]),
            current_user=user,
        )

        url = new_sr.get_app_url()
        title = breadcrumbs.get_title_breadcrumbs(
            page_cls=BulkRunnerPage, sr=new_sr, pr=run_dict["published_run"]
        ).title_with_prefix()
        bulk_run_urls.append((url, title))


def render_success_alert(success_alert: gui.AlertDialogRef, bulk_run_urls: list[str]):
    with (
        gui.alert_dialog(success_alert, modal_title="#### ✅ Evaluation submitted"),
        gui.div(
            className="d-flex flex-column justify-content-center align-items-center gap-2"
        ),
    ):
        for url, title in bulk_run_urls:
            gui.write(
                f'##### <i class="fa fa-external-link"></i> <a href="{url}" target="_blank">{title}</a>',
                unsafe_allow_html=True,
            )
