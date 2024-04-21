import typing

from bots.models import PublishedRun, SavedRun, WorkflowMetadata
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs
from daras_ai_v2.meta_preview_url import meta_preview_url

if typing.TYPE_CHECKING:
    from routers.root import RecipeTabs
    from daras_ai_v2.base import BasePage

SEP = " • "
TITLE_SUFFIX = "Gooey.AI"


def build_meta_tags(
    *,
    url: str,
    page: "BasePage",
    state: dict,
    run_id: str,
    uid: str,
    example_id: str,
) -> list[dict]:
    sr, pr = page.get_runs_from_query_params(example_id, run_id, uid)
    metadata = page.workflow.get_or_create_metadata()

    title = meta_title_for_page(
        page=page,
        metadata=metadata,
        sr=sr,
        pr=pr,
        tab=page.tab,
    )
    description = meta_description_for_page(
        metadata=metadata,
        pr=pr,
    )
    image = meta_image_for_page(
        page=page,
        state=state,
        sr=sr,
        metadata=metadata,
        pr=pr,
    )
    canonical_url = canonical_url_for_page(page=page, sr=sr, pr=pr)
    robots = robots_tag_for_page(page=page, sr=sr, pr=pr)

    return raw_build_meta_tags(
        url=url,
        title=title,
        description=description,
        image=image,
        canonical_url=canonical_url,
        robots=robots,
    )


def raw_build_meta_tags(
    *,
    url: str,
    title: str,
    description: str | None = None,
    image: str | None = None,
    canonical_url: str | None = None,
    robots: str | None = None,
) -> list[dict[str, str]]:
    ret = [
        dict(title=title),
        dict(name="title", content=title),
        dict(property="og:type", content="website"),
        dict(property="og:url", content=url),
        dict(property="og:title", content=title),
        dict(property="twitter:card", content="summary_large_image"),
        dict(property="twitter:url", content=url),
        dict(property="twitter:title", content=title),
    ]

    if description:
        ret += [
            dict(name="description", content=description),
            dict(property="og:description", content=description),
            dict(property="twitter:description", content=description),
        ]

    if image:
        ret += [
            dict(name="image", content=image),
            dict(property="og:image", content=image),
            dict(property="twitter:image", content=image),
        ]

    if canonical_url:
        ret += [dict(tagName="link", rel="canonical", href=canonical_url)]

    if robots:
        ret += [dict(name="robots", content=robots)]

    return ret


def meta_title_for_page(
    *,
    page: "BasePage",
    metadata: WorkflowMetadata,
    sr: SavedRun,
    pr: PublishedRun | None,
    tab: "RecipeTabs",
) -> str:
    from routers.root import RecipeTabs

    match tab:
        case RecipeTabs.examples:
            ret = f"{tab.label}: {metadata.meta_title}"
        case RecipeTabs.run_as_api | RecipeTabs.integrations:
            page_title = meta_title_for_page(
                page=page, metadata=metadata, sr=sr, pr=pr, tab=RecipeTabs.run
            )
            return f"{tab.label} for {page_title}"
        case RecipeTabs.history | RecipeTabs.saved:
            ret = f"{tab.label} for {metadata.short_title}"
        case _ if pr and pr.saved_run == sr and pr.is_root():
            # for root page
            ret = page.get_dynamic_meta_title() or metadata.meta_title
        case _:
            # non-root runs and examples
            parts = []

            tbreadcrumbs = get_title_breadcrumbs(page, sr, pr)
            parts.append(tbreadcrumbs.h1_title)

            # use the short title for non-root examples
            part = metadata.short_title
            if tbreadcrumbs.published_title:
                part = f"{pr.title} {part}"
            # add the creator's name
            user = sr.get_creator()
            if user and user.display_name:
                part += f" by {user.display_name}"
            parts.append(part)

            ret = SEP.join(parts)

    return f"{ret} {SEP} {TITLE_SUFFIX}"


def meta_description_for_page(
    *,
    metadata: WorkflowMetadata,
    pr: PublishedRun | None,
) -> str:
    if pr and not pr.is_root():
        description = pr.notes or metadata.meta_description
    else:
        description = metadata.meta_description

    if not (pr and pr.is_root()) or not description:
        # for all non-root examples, or when there is no other description
        description += SEP + "AI API, workflow & prompt shared on Gooey.AI."

    return description


def meta_image_for_page(
    *,
    page: "BasePage",
    state: dict,
    metadata: WorkflowMetadata,
    sr: SavedRun,
    pr: PublishedRun | None,
) -> str | None:
    if pr and pr.saved_run == sr and pr.is_root():
        file_url = metadata.meta_image or page.preview_image(state)
    else:
        file_url = page.preview_image(state)

    return meta_preview_url(
        file_url=file_url,
        fallback_img=page.fallback_preivew_image(),
    )


def canonical_url_for_page(
    *,
    page: "BasePage",
    sr: SavedRun,
    pr: PublishedRun | None,
) -> str:
    """
    Assumes that `page.tab` is a valid tab defined in RecipeTabs
    """
    from routers.root import RecipeTabs

    kwargs = {}
    if page.tab in [RecipeTabs.run, RecipeTabs.run_as_api, RecipeTabs.integrations]:
        if pr and pr.saved_run == sr and pr.is_root():
            pass
        elif pr and pr.saved_run == sr:
            kwargs = {"example_id": pr.published_run_id}
        else:
            kwargs = {"run_id": sr.run_id, "uid": sr.uid}
    return page.app_url(page.tab, **kwargs)


def robots_tag_for_page(
    *,
    page: "BasePage",
    sr: SavedRun,
    pr: PublishedRun | None,
) -> str:
    from routers.root import RecipeTabs

    is_root = pr and pr.saved_run == sr and pr.is_root()
    is_example = pr and pr.saved_run == sr and not pr.is_root()

    match page.tab:
        case RecipeTabs.run if is_root or is_example:
            no_follow, no_index = False, False
        case RecipeTabs.run:  # ordinary run (not example)
            no_follow, no_index = False, True
        case RecipeTabs.examples:
            no_follow, no_index = False, False
        case RecipeTabs.run_as_api:
            no_follow, no_index = False, True
        case RecipeTabs.integrations:
            no_follow, no_index = True, True
        case RecipeTabs.history:
            no_follow, no_index = True, True
        case RecipeTabs.saved:
            no_follow, no_index = True, True
        case _:
            raise ValueError(f"Unknown tab: {page.tab}")

    parts = []
    if no_follow:
        parts.append("nofollow")
    if no_index:
        parts.append("noindex")
    return ",".join(parts)


def get_is_indexable_for_page(
    *,
    page: "BasePage",
    sr: SavedRun,
    pr: PublishedRun | None,
) -> bool:
    from routers.root import RecipeTabs

    if pr and pr.saved_run == sr and pr.is_root():
        # index all tabs on root
        return True

    return bool(pr and pr.saved_run == sr and page.tab == RecipeTabs.run)
