import typing

import gooey_gui as gui
from django.db.models import Q
from furl import furl

from app_users.models import AppUser
from bots.models import PublishedRun, PublishedRunVisibility, SavedRun, Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs
from daras_ai_v2.enum_selector_widget import BLANK_OPTION
from daras_ai_v2.fastapi_tricks import resolve_url
from daras_ai_v2.query_params_util import extract_query_params


def workflow_url_input(
    *,
    page_cls: typing.Type[BasePage],
    key: str,
    internal_state: dict,
    del_key: str = None,
    current_user: AppUser | None = None,
    allow_none: bool = False,
    include_root: bool = True
) -> tuple[typing.Type[BasePage], SavedRun, PublishedRun | None] | None:
    init_workflow_selector(internal_state, key)

    col1, col2, col3, col4 = gui.columns([9, 1, 1, 1], responsive=False)
    if not internal_state.get("workflow") and internal_state.get("url"):
        with col1:
            url = gui.text_input(
                "",
                key=key,
                value=internal_state.get("url"),
                placeholder="https://gooey.ai/.../?run_id=...",
            )
        with col2:
            edit_done_button(key)
    else:
        internal_state["workflow"] = page_cls.workflow
        with col1:
            options = get_published_run_options(
                page_cls, current_user=current_user, include_root=include_root
            )
            options.update(internal_state.get("--added_workflows", {}))
            with gui.div(className="pt-1"):
                url = gui.selectbox(
                    "",
                    key=key,
                    options=options,
                    value=internal_state.get("url"),
                    format_func=lambda x: options[x] if x else BLANK_OPTION,
                    allow_none=allow_none,
                )
                if not url:
                    return
        with col2:
            edit_button(key)
    with col3:
        gui.url_button(url)
    with col4:
        if del_key:
            del_button(del_key)

    try:
        ret = url_to_runs(url)
    except Exception as e:
        ret = None
        gui.error(repr(e))
    internal_state["url"] = url
    return ret


def edit_done_button(key: str):
    gui.button(
        '<i class="fa-regular fa-square-check text-success"></i>',
        key=key + ":edit-done",
        type="tertiary",
    )


def edit_button(key: str):
    gui.button(
        '<i class="fa-regular fa-pencil text-warning"></i>',
        key=key + ":edit-mode",
        type="tertiary",
    )


def del_button(key: str):
    gui.button(
        '<i class="fa-regular fa-trash text-danger"></i>',
        key=key,
        type="tertiary",
    )


def init_workflow_selector(
    internal_state: dict,
    key: str,
) -> dict:
    if gui.session_state.get(key + ":edit-done"):
        gui.session_state.pop(key + ":edit-mode", None)
        gui.session_state.pop(key + ":edit-done", None)
        gui.session_state.pop(key, None)

    if gui.session_state.get(key + ":edit-mode"):
        internal_state.pop("workflow", None)

    elif not internal_state.get("workflow") and internal_state.get("url"):
        try:
            _, sr, pr = url_to_runs(str(internal_state["url"]))
        except Exception:
            return

        workflow = sr.workflow
        page_cls = Workflow(workflow).page_cls
        if pr and pr.saved_run_id == sr.id:
            url = pr.get_app_url()
        else:
            url = sr.get_app_url()
        title = get_title_breadcrumbs(page_cls, sr, pr).h1_title

        internal_state["workflow"] = workflow
        internal_state["url"] = url

        internal_state.setdefault("--added_workflows", {})[url] = title


def url_to_runs(
    url: str,
) -> tuple[typing.Type[BasePage], SavedRun, PublishedRun | None]:
    from daras_ai_v2.all_pages import page_slug_map, normalize_slug

    match = resolve_url(url)
    assert match, "Not a valid Gooey.AI URL"
    page_cls = page_slug_map[normalize_slug(match.matched_params["page_slug"])]
    example_id, run_id, uid = extract_query_params(furl(url).query.params)
    sr, pr = page_cls.get_runs_from_query_params(
        example_id or match.matched_params.get("example_id"), run_id, uid
    )
    return page_cls, sr, pr


@gui.cache_in_session_state
def get_published_run_options(
    page_cls: typing.Type[BasePage],
    current_user: AppUser | None = None,
    include_root: bool = True,
) -> dict[str, str]:
    # approved examples
    pr_query = Q(is_approved_example=True, visibility=PublishedRunVisibility.PUBLIC)

    if current_user:
        # user's saved runs
        pr_query |= Q(created_by=current_user)

    saved_runs_and_examples = PublishedRun.objects.filter(
        pr_query,
        workflow=page_cls.workflow,
    ).exclude(published_run_id="")
    saved_runs_and_examples = sorted(
        saved_runs_and_examples,
        reverse=True,
        key=lambda pr: (
            int(
                current_user and pr.created_by == current_user or False
            ),  # user's saved first
            pr.example_priority,  # higher priority first
            pr.updated_at,  # newer first
        ),
    )
    options_dict = {
        pr.get_app_url(): get_title_breadcrumbs(page_cls, pr.saved_run, pr).h1_title
        for pr in saved_runs_and_examples
    }

    if include_root:
        # include root recipe if requested
        options_dict = {
            page_cls.get_root_published_run().get_app_url(): "Default",
        } | options_dict

    return options_dict
