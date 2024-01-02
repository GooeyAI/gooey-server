from firebase_admin import auth

from bots.models import PublishedRun, SavedRun
from daras_ai.image_input import truncate_text_words
from daras_ai_v2.base import BasePage
from daras_ai_v2.meta_preview_url import meta_preview_url


def build_meta_tags(
    *,
    url: str,
    page: BasePage,
    state: dict,
) -> list[dict]:
    sr = page.get_current_sr()
    published_run = page.get_current_published_run()

    title = meta_title_for_page(
        page=page,
        state=state,
        sr=sr,
        published_run=published_run,
    )
    description = meta_description_for_page(
        page=page,
        state=state,
        sr=sr,
        published_run=published_run,
    )
    image = meta_image_for_page(
        page=page,
        state=state,
        sr=sr,
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
    state: dict,
    sr: SavedRun,
    published_run: PublishedRun | None,
) -> str:
    if (
        published_run
        and published_run.is_root_example()
        and published_run.saved_run == sr
    ):
        # on root page
        return page.workflow.metadata.meta_title + " | Gooey.AI"

    title = page.get_page_title()
    if published_run and published_run.saved_run != sr:
        # fork or stale version of a published-run: add user's name
        user = sr.get_creator()
        if user and user.display_name:
            title = user_name_possesive(user.display_name) + " " + title

    return f"{title} | AI API, workflow & prompt shared on Gooey.AI"


def user_name_possesive(name: str) -> str:
    if name.endswith("s"):
        return name + "'"
    else:
        return name + "'s"


def meta_description_for_page(
    *,
    page: BasePage,
    state: dict,
    sr: SavedRun,
    published_run: PublishedRun | None,
) -> str:
    if published_run and not published_run.is_root_example():
        description = published_run.notes
    else:
        description = page.workflow.metadata.meta_description

    if not (published_run and published_run.is_root_example()) or not description:
        # for all non-root examples, or when there is no other description
        description += " AI API, workflow & prompt shared on Gooey.AI."

    return description


def meta_image_for_page(
    *,
    page: BasePage,
    state: dict,
    sr: SavedRun,
    published_run: PublishedRun | None,
) -> str | None:
    return meta_preview_url(
        file_url=page.workflow.metadata.meta_image or page.preview_image(state),
        fallback_img=page.fallback_preivew_image(),
    )
