from furl import furl

from bots.models import PublishedRun, SavedRun, WorkflowMetadata
from daras_ai_v2 import settings
from daras_ai_v2.base import BasePage, slugify
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

    return raw_build_meta_tags(
        url=url,
        title=title,
        description=description,
        image=image,
        canonical_url=canonical_url,
    )


def raw_build_meta_tags(
    *,
    url: str,
    title: str,
    description: str | None = None,
    image: str | None = None,
    canonical_url: str | None = None,
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
):
    """
    Assumes that `page.tab` is a valid tab defined in MenuTabs
    """

    latest_slug = page.slug_versions[-1]  # recipe slug

    if (
        pr
        and pr.saved_run == sr
        and not pr.is_root()
        and page.tab in {MenuTabs.run, MenuTabs.run_as_api, MenuTabs.integrations}
    ):
        # on non-root saved workflows, when tab is Run / API / Integrations
        # the page content depends on the example_id an must be indexed
        pr_slug = slugify(pr.title) if pr.title else ""
        query_params = {"example_id": pr.published_run_id}
    else:
        # for all other runs and the root workflow, let only the root workflow page be indexed
        pr_slug = ""
        query_params = {}

    return str(
        furl(
            str(settings.APP_BASE_URL),
            query_params=query_params,
        )
        / latest_slug
        / pr_slug
        / MenuTabs.paths[page.tab]
        / "/"  # preserve trailing slash
    )
