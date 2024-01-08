import typing

import gooey_ui as st
from bots.models import (
    SavedRun,
    PublishedRun,
)
from daras_ai.image_input import truncate_text_words

if typing.TYPE_CHECKING:
    from daras_ai_v2.base import BasePage


class TitleUrl(typing.NamedTuple):
    title: str
    url: str


class TitleBreadCrumbs(typing.NamedTuple):
    h1_title: str
    root_title: TitleUrl | None
    published_title: TitleUrl | None


def render_breadcrumbs(breadcrumbs: TitleBreadCrumbs):
    st.html(
        """
        <style>
        @media (min-width: 1024px) {
            .breadcrumb-item {
                font-size: 1.25rem !important;
            }
        }

        @media (max-width: 1024px) {
            .breadcrumb-item {
                font-size: 0.85rem !important;
                padding-top: 6px;
            }
        }
        </style>
        """
    )

    if not (breadcrumbs.root_title or breadcrumbs.published_title):
        # avoid empty space when breadcrumbs are not rendered
        return

    with st.breadcrumbs():
        if breadcrumbs.root_title:
            st.breadcrumb_item(
                breadcrumbs.root_title.title,
                link_to=breadcrumbs.root_title.url,
                className="text-muted",
            )
        if breadcrumbs.published_title:
            st.breadcrumb_item(
                breadcrumbs.published_title.title,
                link_to=breadcrumbs.published_title.url,
            )


def get_title_breadcrumbs(
    page_cls: typing.Union["BasePage", typing.Type["BasePage"]],
    sr: SavedRun,
    pr: PublishedRun | None,
) -> TitleBreadCrumbs:
    if pr and sr == pr.saved_run and not pr.published_run_id:
        # when published_run.published_run_id is blank, the run is the root example
        return TitleBreadCrumbs(page_cls.get_recipe_title(), None, None)

    # the title on the saved root / the hardcoded title
    recipe_title = page_cls.get_root_published_run().title or page_cls.title
    prompt_title = truncate_text_words(
        page_cls.preview_input(sr.to_dict()) or "",
        maxlen=60,
    ).replace("\n", " ")

    root_title = TitleUrl(recipe_title, page_cls.app_url())

    if pr and sr == pr.saved_run:
        # published run root
        return TitleBreadCrumbs(
            pr.title or prompt_title or recipe_title,
            root_title,
            None,
        )

    if not pr or not pr.published_run_id:
        # run created directly from recipe root
        h1_title = prompt_title or f"Run: {recipe_title}"
        return TitleBreadCrumbs(h1_title, root_title, None)

    # run created from a published run
    h1_title = prompt_title or f"Run: {pr.title or recipe_title}"
    published_title = TitleUrl(
        pr.title or f"Fork {pr.published_run_id}", pr.get_app_url()
    )
    return TitleBreadCrumbs(h1_title, root_title, published_title)
