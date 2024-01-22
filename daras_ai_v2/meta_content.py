from django.utils.text import slugify
from furl import furl

from bots.models import PublishedRun, SavedRun, WorkflowMetadata
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs
from daras_ai_v2.meta_preview_url import meta_preview_url
from daras_ai_v2.tabs_widget import MenuTabs

sep = " • "


def build_meta_tags(
    *,
    url: str,
    page: BasePage,
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
    canonical_url = canonical_url_for_page(
        page=page,
        state=state,
        sr=sr,
        metadata=metadata,
        pr=pr,
    )
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
    page: BasePage,
    metadata: WorkflowMetadata,
    sr: SavedRun,
    pr: PublishedRun | None,
) -> str:
    tbreadcrumbs = get_title_breadcrumbs(page, sr, pr)

    parts = []
    if tbreadcrumbs.published_title or tbreadcrumbs.root_title:
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
    else:
        # for root recipe, a longer, SEO-friendly title
        parts.append(metadata.meta_title)

    parts.append("Gooey.AI")
    return sep.join(parts)


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
        description += sep + "AI API, workflow & prompt shared on Gooey.AI."

    return description


def meta_image_for_page(
    *,
    page: BasePage,
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
    page: BasePage,
    state: dict,
    metadata: WorkflowMetadata,
    sr: SavedRun,
    pr: PublishedRun | None,
) -> str:
    """
    Assumes that `page.tab` is a valid tab defined in MenuTabs
    """

    latest_slug = page.slug_versions[-1]  # for recipe
    recipe_url = furl(str(settings.APP_BASE_URL)) / latest_slug

    if pr and pr.saved_run == sr and pr.is_root():
        query_params = {}
        pr_slug = ""
    elif pr and pr.saved_run == sr:
        query_params = {"example_id": pr.published_run_id}
        pr_slug = (pr.title and slugify(pr.title)) or ""
    else:
        query_params = {"run_id": sr.run_id, "uid": sr.uid}
        pr_slug = ""

    tab_path = MenuTabs.paths[page.tab]
    match page.tab:
        case MenuTabs.examples:
            # no query params / run_slug in this case
            return str(recipe_url / tab_path / "/")
        case MenuTabs.history, MenuTabs.saved:
            # no run slug in this case
            return str(furl(recipe_url, query_params=query_params) / tab_path / "/")
        case _:
            # all other cases
            return str(
                furl(recipe_url, query_params=query_params) / pr_slug / tab_path / "/"
            )


def robots_tag_for_page(
    *,
    page: BasePage,
    sr: SavedRun,
    pr: PublishedRun | None,
) -> str:
    is_root = pr and pr.saved_run == sr and pr.is_root()
    is_example = pr and pr.saved_run == sr and not pr.is_root()

    match page.tab:
        case MenuTabs.run if is_root or is_example:
            no_follow, no_index = False, False
        case MenuTabs.run:  # ordinary run (not example)
            no_follow, no_index = False, True
        case MenuTabs.examples:
            no_follow, no_index = False, False
        case MenuTabs.run_as_api:
            no_follow, no_index = False, True
        case MenuTabs.integrations:
            no_follow, no_index = True, True
        case MenuTabs.history:
            no_follow, no_index = True, True
        case MenuTabs.saved:
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
    page: BasePage,
    sr: SavedRun,
    pr: PublishedRun | None,
) -> bool:
    if pr and pr.saved_run == sr and pr.is_root():
        # index all tabs on root
        return True

    return bool(pr and pr.saved_run == sr and page.tab == MenuTabs.run)
