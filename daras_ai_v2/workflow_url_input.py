import typing

import gooey_gui as gui
from furl import furl

from app_users.models import AppUser
from bots.models import PublishedRun, SavedRun, Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs
from daras_ai_v2.enum_selector_widget import BLANK_OPTION
from daras_ai_v2.fastapi_tricks import resolve_url
from daras_ai_v2.published_run_options import (
    AsyncSelectProps,
    get_published_run_options_page,
    get_published_run_options_url,
    iter_published_run_options,
)
from daras_ai_v2.query_params_util import extract_query_params


def workflow_url_input(
    *,
    page_cls: typing.Type[BasePage],
    key: str,
    internal_state: dict,
    del_key: str = None,
    current_user: AppUser | None = None,
    allow_none: bool = False,
    include_root: bool = True,
) -> tuple[typing.Type[BasePage], SavedRun, PublishedRun | None] | None:
    init_workflow_selector(internal_state, key)

    with gui.div(className="d-flex align-items-center"):
        if not internal_state.get("workflow") and internal_state.get("url"):
            with gui.div(className="flex-grow-1"):
                url = gui.text_input(
                    "",
                    key=key,
                    value=internal_state.get("url"),
                    placeholder="https://gooey.ai/.../?run_id=...",
                )
            edit_done_button(key)
        else:
            internal_state["workflow"] = page_cls.workflow
            with gui.div(className="flex-grow-1"):
                url = render_published_run_selectbox(
                    page_cls=page_cls,
                    key=key,
                    value=internal_state.get("url"),
                    current_user=current_user,
                    include_root=include_root,
                    selected_options=internal_state.get("--added_workflows", {}),
                    allow_none=allow_none,
                )
                if not url:
                    return
            edit_button(key)
        gui.url_button(url)
        if del_key:
            del_button(del_key)

    try:
        ret = url_to_runs(url)
    except Exception as e:
        ret = None
        gui.error(repr(e))
    internal_state["url"] = url
    return ret


def render_published_run_selectbox(
    *,
    page_cls: typing.Type[BasePage],
    key: str,
    value: str | None,
    current_user: AppUser | None = None,
    include_root: bool = True,
    selected_options: dict[str, str] | None = None,
    lazy_options: bool = False,
    allow_none: bool = False,
) -> str | None:
    options, async_props = get_published_run_selectbox_props(
        page_cls=page_cls,
        current_user=current_user,
        include_root=include_root,
        selected_url=value,
        selected_options=selected_options,
        lazy_options=lazy_options,
    )
    if allow_none:

        def format_func(option_key):
            if option_key:
                return options[option_key]
            return BLANK_OPTION

    else:
        format_func = options.__getitem__
    with gui.div(className="pt-1"):
        return gui.selectbox(
            "",
            key=key,
            options=options,
            value=value,
            format_func=format_func,
            allow_none=allow_none,
            **async_props,
        )


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


def get_published_run_selectbox_props(
    *,
    page_cls: typing.Type[BasePage],
    current_user: AppUser | None = None,
    include_root: bool = True,
    selected_url: str | None = None,
    selected_options: dict[str, str] | None = None,
    lazy_options: bool = False,
) -> tuple[dict[str, str], AsyncSelectProps | dict]:
    extra_options = selected_options or {}

    if not lazy_options:
        options = get_cached_all_published_run_options(
            page_cls=page_cls,
            current_user=current_user,
            include_root=include_root,
        )
        return merge_extra_published_run_options(options, extra_options), {}

    if selected_url:
        options = {
            selected_url: get_selected_run_option_label(
                page_cls=page_cls,
                selected_url=selected_url,
                selected_options=extra_options,
            )
        }
        next_options_page = 0
    else:
        options, next_options_page = get_cached_published_run_options_first_page(
            page_cls=page_cls,
            current_user=current_user,
            include_root=include_root,
        )

    return merge_extra_published_run_options(options, extra_options), AsyncSelectProps(
        asyncOptionsUrl=get_published_run_options_url(
            page_cls=page_cls,
            include_root=include_root,
        ),
        nextOptionsPage=next_options_page,
    )


@gui.cache_in_session_state
def get_cached_all_published_run_options(
    page_cls: typing.Type[BasePage],
    current_user: AppUser | None,
    include_root: bool,
) -> dict[str, str]:
    return dict(
        iter_published_run_options(
            page_cls=page_cls,
            current_user=current_user,
            include_root=include_root,
            query="",
        )
    )


@gui.cache_in_session_state
def get_cached_published_run_options_first_page(
    page_cls: typing.Type[BasePage],
    current_user: AppUser | None,
    include_root: bool,
) -> tuple[dict[str, str], int | None]:
    return get_published_run_options_page(
        page_cls=page_cls,
        current_user=current_user,
        include_root=include_root,
        page=0,
    )


def merge_extra_published_run_options(
    options: dict[str, str],
    extra_options: dict[str, str] | None,
) -> dict[str, str]:
    merged = dict(options)
    for url, label in (extra_options or {}).items():
        merged.setdefault(url, label)
    return merged


def get_selected_run_option_label(
    *,
    page_cls: typing.Type[BasePage],
    selected_url: str,
    selected_options: dict[str, str] | None = None,
) -> str:
    label = (selected_options or {}).get(selected_url)
    if label:
        return label
    try:
        selected_page_cls, sr, pr = url_to_runs(selected_url)
    except (AssertionError, KeyError, PublishedRun.DoesNotExist, SavedRun.DoesNotExist):
        return selected_url
    if selected_page_cls.workflow != page_cls.workflow:
        return selected_url
    return (
        get_title_breadcrumbs(selected_page_cls, sr, pr).title_with_prefix()
        or selected_url
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
        title = get_title_breadcrumbs(page_cls, sr, pr).title_with_prefix()

        internal_state["workflow"] = workflow
        internal_state["url"] = url

        internal_state.setdefault("--added_workflows", {})[url] = title


def url_to_runs(
    url: str,
) -> tuple[typing.Type[BasePage], SavedRun, PublishedRun]:
    from daras_ai_v2.all_pages import page_slug_map, normalize_slug

    assert url, "URL is required"
    match = resolve_url(url)
    assert match, "Not a valid Gooey.AI URL"
    page_cls = page_slug_map[normalize_slug(match.matched_params["page_slug"])]
    example_id, run_id, uid = extract_query_params(furl(url).query.params)
    sr, pr = page_cls.get_sr_pr_from_query_params(
        example_id=example_id or match.matched_params.get("example_id") or "",
        run_id=run_id,
        uid=uid,
    )
    return page_cls, sr, pr
