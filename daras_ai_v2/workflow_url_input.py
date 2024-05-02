import typing

from django.db.models import Q
from furl import furl

import gooey_ui as st
from app_users.models import AppUser
from bots.models import PublishedRun, PublishedRunVisibility, SavedRun
from daras_ai_v2.base import BasePage
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs
from daras_ai_v2.enum_selector_widget import BLANK_OPTION
from daras_ai_v2.fastapi_tricks import resolve_url
from daras_ai_v2.query_params_util import extract_query_params
from gooey_ui.components.url_button import url_button


def workflow_url_input(
    *,
    page_cls: typing.Type[BasePage],
    key: str,
    internal_state: dict,
    del_key: str = None,
    current_user: AppUser | None = None,
    allow_none: bool = False,
):
    init_workflow_selector(internal_state, key)

    col1, col2, col3 = st.columns([10, 1, 1], responsive=False)
    if not internal_state.get("workflow") and internal_state.get("url"):
        with col1:
            url = st.text_input(
                "",
                key=key,
                value=internal_state.get("url"),
                placeholder="https://gooey.ai/.../?run_id=...",
            )
    else:
        internal_state["workflow"] = page_cls.workflow
        with col1:
            scol1, scol2 = st.columns([11, 1], responsive=False)
        with scol1:
            options = get_published_run_options(page_cls, current_user=current_user)
            with st.div(className="pt-1"):
                url = st.selectbox(
                    "",
                    key=key,
                    options=options,
                    value=internal_state.get("url"),
                    format_func=lambda x: options[x] if x else BLANK_OPTION,
                    allow_none=allow_none,
                )
                if not url:
                    return
        with scol2:
            edit_button(key + ":editmode")
    with col2:
        url_button(url)
    with col3:
        if del_key:
            del_button(del_key)

    try:
        url_to_runs(url)
    except Exception as e:
        st.error(repr(e))
    internal_state["url"] = url


def edit_button(key: str):
    st.button(
        '<i class="fa-regular fa-pencil text-warning"></i>',
        key=key,
        type="tertiary",
    )


def del_button(key: str):
    st.button(
        '<i class="fa-regular fa-trash text-danger"></i>',
        key=key,
        type="tertiary",
    )


def init_workflow_selector(internal_state: dict, key: str):
    if st.session_state.get(key + ":editmode"):
        internal_state.pop("workflow", None)
    elif not internal_state.get("workflow") and internal_state.get("url"):
        try:
            _, sr, pr = url_to_runs(str(internal_state["url"]))
        except Exception:
            return
        else:
            if (
                pr
                and pr.saved_run == sr
                and pr.visibility == PublishedRunVisibility.PUBLIC
                and (pr.is_approved_example or pr.is_root())
            ):
                internal_state["workflow"] = pr.workflow
                internal_state["url"] = pr.get_app_url()


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


@st.cache_in_session_state
def get_published_run_options(
    page_cls: typing.Type[BasePage],
    current_user: AppUser | None = None,
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

    options = {
        # root recipe
        page_cls.get_root_published_run().get_app_url(): "Default",
    } | {
        pr.get_app_url(): get_title_breadcrumbs(page_cls, pr.saved_run, pr).h1_title
        for pr in saved_runs_and_examples
    }

    return options
