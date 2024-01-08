from bots.models import PublishedRun, SavedRun, WorkflowMetadata
from daras_ai_v2.base import BasePage
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs
from daras_ai_v2.meta_preview_url import meta_preview_url

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
    sr, published_run = page.get_runs_from_query_params(example_id, run_id, uid)
    metadata = page.workflow.get_or_create_metadata()

    title = meta_title_for_page(
        page=page,
        metadata=metadata,
        sr=sr,
        published_run=published_run,
    )
    description = meta_description_for_page(
        metadata=metadata,
        published_run=published_run,
    )
    image = meta_image_for_page(
        page=page,
        state=state,
        sr=sr,
        metadata=metadata,
        published_run=published_run,
    )

    return raw_build_meta_tags(
        url=url,
        title=title,
        description=description,
        image=image,
    )


def raw_build_meta_tags(
    *,
    url: str,
    title: str,
    description: str | None = None,
    image: str | None = None,
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
    return ret


def meta_title_for_page(
    *,
    page: BasePage,
    metadata: WorkflowMetadata,
    sr: SavedRun,
    published_run: PublishedRun | None,
) -> str:
    tbreadcrumbs = get_title_breadcrumbs(page, sr, published_run)

    parts = []
    if tbreadcrumbs.published_title or tbreadcrumbs.root_title:
        parts.append(tbreadcrumbs.h1_title)
        # use the short title for non-root examples
        part = metadata.short_title
        if tbreadcrumbs.published_title:
            part = f"{published_run.title} {part}"
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
    published_run: PublishedRun | None,
) -> str:
    if published_run and not published_run.is_root_example():
        description = published_run.notes or metadata.meta_description
    else:
        description = metadata.meta_description

    if not (published_run and published_run.is_root_example()) or not description:
        # for all non-root examples, or when there is no other description
        description += sep + "AI API, workflow & prompt shared on Gooey.AI."

    return description


def meta_image_for_page(
    *,
    page: BasePage,
    state: dict,
    metadata: WorkflowMetadata,
    sr: SavedRun,
    published_run: PublishedRun | None,
) -> str | None:
    if (
        published_run
        and published_run.saved_run == sr
        and published_run.is_root_example()
    ):
        file_url = metadata.meta_image or page.preview_image(state)
    else:
        file_url = page.preview_image(state)

    return meta_preview_url(
        file_url=file_url,
        fallback_img=page.fallback_preivew_image(),
    )
