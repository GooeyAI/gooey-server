import typing

from django.db.models import Case, IntegerField, Q, QuerySet, Value, When
from furl import furl

from app_users.models import AppUser
from bots.models import PublishedRun
from daras_ai_v2.base import BasePage
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs

PUBLISHED_RUN_OPTIONS_PAGE_SIZE = 20


class AsyncSelectProps(typing.TypedDict):
    asyncOptionsUrl: str
    nextOptionsPage: int | None


def get_published_run_options_page(
    *,
    page_cls: typing.Type[BasePage],
    current_user: AppUser | None = None,
    include_root: bool = True,
    q: str | None = None,
    page: int = 0,
    page_size: int = PUBLISHED_RUN_OPTIONS_PAGE_SIZE,
) -> tuple[dict[str, str], int | None]:
    query = (q or "").strip().casefold()
    if query:
        return paginate_published_run_option_matches(
            page_cls=page_cls,
            current_user=current_user,
            include_root=include_root,
            query=query,
            page=page,
            page_size=page_size,
        )
    return paginate_published_run_options_from_db(
        page_cls=page_cls,
        current_user=current_user,
        include_root=include_root,
        page=page,
        page_size=page_size,
    )


def paginate_published_run_options_from_db(
    *,
    page_cls: typing.Type[BasePage],
    current_user: AppUser | None,
    include_root: bool,
    page: int,
    page_size: int,
) -> tuple[dict[str, str], int | None]:
    start = page * page_size
    window: list[tuple[str, str]] = []

    prefix_len = 0
    if include_root:
        prefix_len = 1
        if start == 0:
            window.append(get_root_option(page_cls))

    db_offset = max(0, start - prefix_len)
    db_limit = page_size + 1 - len(window)
    qs_slice = get_published_runs_options_queryset(page_cls, current_user)[
        db_offset : db_offset + db_limit
    ]
    for pr in qs_slice:
        window.append(
            (
                pr.get_app_url(),
                get_title_breadcrumbs(page_cls, pr.saved_run, pr).title_with_prefix(),
            )
        )

    return finalize_options_page(window, page, page_size)


def paginate_published_run_option_matches(
    *,
    page_cls: typing.Type[BasePage],
    current_user: AppUser | None,
    include_root: bool,
    query: str,
    page: int,
    page_size: int,
) -> tuple[dict[str, str], int | None]:
    start = page * page_size
    window: list[tuple[str, str]] = []
    matches = iter_published_run_options(
        page_cls=page_cls,
        current_user=current_user,
        include_root=include_root,
        query=query,
    )
    for index, pair in enumerate(matches):
        if index < start:
            continue
        window.append(pair)
        if len(window) > page_size:
            break
    return finalize_options_page(window, page, page_size)


def finalize_options_page(
    window: list[tuple[str, str]],
    page: int,
    page_size: int,
) -> tuple[dict[str, str], int | None]:
    options = dict(window[:page_size])
    if len(window) > page_size:
        return options, page + 1
    return options, None


def iter_published_run_options(
    *,
    page_cls: typing.Type[BasePage],
    current_user: AppUser | None,
    include_root: bool,
    query: str,
) -> typing.Iterator[tuple[str, str]]:
    seen_values: set[str] = set()

    if include_root:
        value, label = get_root_option(page_cls)
        seen_values.add(value)
        if option_matches_query(value=value, label=label, query=query):
            yield value, label

    for pr in get_published_runs_options_queryset(page_cls, current_user).iterator():
        value = pr.get_app_url()
        if value in seen_values:
            continue
        seen_values.add(value)
        label = get_title_breadcrumbs(page_cls, pr.saved_run, pr).title_with_prefix()
        if option_matches_query(value=value, label=label, query=query):
            yield value, label


def get_root_option(page_cls: typing.Type[BasePage]) -> tuple[str, str]:
    return page_cls.get_root_pr().get_app_url(), "Default"


def option_matches_query(*, value: str, label: str, query: str) -> bool:
    if not query:
        return True
    return query in label.casefold() or query in value.casefold()


def get_published_runs_options_queryset(
    page_cls: typing.Type[BasePage],
    current_user: AppUser | None = None,
) -> QuerySet[PublishedRun]:
    pr_query = PublishedRun.approved_example_q()
    current_user_id = current_user and current_user.id
    if current_user_id:
        pr_query |= Q(created_by_id=current_user_id)
        current_user_priority = Case(
            When(created_by_id=current_user_id, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )
    else:
        current_user_priority = Value(0, output_field=IntegerField())
    return (
        PublishedRun.objects.select_related("saved_run")
        .filter(
            pr_query,
            workflow=page_cls.workflow,
        )
        .annotate(current_user_priority=current_user_priority)
        .order_by("-current_user_priority", "-example_priority", "-updated_at")
    )


def get_published_run_options_url(
    *,
    page_cls: typing.Type[BasePage],
    include_root: bool = True,
) -> str:
    return str(
        furl("/__/published-run-options/").add(
            {
                "page_slug": page_cls.slug_versions[-1],
                "include_root": include_root,
            }
        )
    )


def get_selectable_workflow_page_cls(page_slug: str) -> typing.Type[BasePage]:
    from daras_ai_v2.all_pages import api_page_slug_map, normalize_slug

    return api_page_slug_map[normalize_slug(page_slug)]
