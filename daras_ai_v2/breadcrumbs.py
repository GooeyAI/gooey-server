import typing

import gooey_gui as gui
from bots.models import (
    SavedRun,
    PublishedRun,
)
from daras_ai.image_input import truncate_text_words

if typing.TYPE_CHECKING:
    from routers.root import RecipeTabs
    from daras_ai_v2.base import BasePage


class TitleUrl(typing.NamedTuple):
    title: str
    url: str


class TitleBreadCrumbs(typing.NamedTuple):
    """
    Breadcrumbs: root_title / published_title
    Title: h1_title
    """

    h1_title: str
    root_title: TitleUrl | None
    published_title: TitleUrl | None

    def has_breadcrumbs(self):
        return bool(self.root_title or self.published_title)


def render_breadcrumbs(breadcrumbs: TitleBreadCrumbs, *, is_api_call: bool = False):
    gui.html(
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

    with gui.breadcrumbs():
        if breadcrumbs.root_title:
            gui.breadcrumb_item(
                breadcrumbs.root_title.title,
                link_to=breadcrumbs.root_title.url,
                className="text-muted",
            )
        if breadcrumbs.published_title:
            gui.breadcrumb_item(
                breadcrumbs.published_title.title,
                link_to=breadcrumbs.published_title.url,
            )

        if is_api_call:
            gui.caption("(API)")


def get_title_breadcrumbs(
    page_cls: typing.Union["BasePage", typing.Type["BasePage"]],
    sr: SavedRun,
    pr: PublishedRun | None,
    tab: "RecipeTabs" = None,
) -> TitleBreadCrumbs:
    from routers.root import RecipeTabs

    is_root = pr and pr.saved_run == sr and pr.is_root()
    is_example = not is_root and pr and pr.saved_run == sr
    is_run = not is_root and not is_example

    recipe_title = page_cls.get_recipe_title()
    prompt_title = truncate_text_words(
        page_cls.preview_input(sr.to_dict()) or "",
        maxlen=60,
    ).replace("\n", " ")

    metadata = page_cls.workflow.get_or_create_metadata()
    root_breadcrumb = TitleUrl(metadata.short_title, page_cls.app_url())

    match tab:
        case RecipeTabs.examples | RecipeTabs.history | RecipeTabs.saved:
            return TitleBreadCrumbs(
                f"{tab.label}: {metadata.short_title}",
                root_title=root_breadcrumb,
                published_title=None,
            )
        case RecipeTabs.run_as_api | RecipeTabs.integrations:
            tbreadcrumbs_on_run = get_title_breadcrumbs(page_cls=page_cls, sr=sr, pr=pr)
            return TitleBreadCrumbs(
                f"{tab.label}: {tbreadcrumbs_on_run.h1_title}",
                root_title=tbreadcrumbs_on_run.root_title or root_breadcrumb,
                published_title=tbreadcrumbs_on_run.published_title,
            )
        case _ if is_root:
            return TitleBreadCrumbs(page_cls.get_recipe_title(), None, None)
        case _ if is_example:
            assert pr is not None
            return TitleBreadCrumbs(
                pr.title or prompt_title or recipe_title,
                root_title=root_breadcrumb,
                published_title=None,
            )
        case _ if is_run:
            if pr and not pr.is_root():
                published_title = TitleUrl(
                    pr.title or f"Fork: {pr.published_run_id}",
                    pr.get_app_url(),
                )
            else:
                published_title = None
            return TitleBreadCrumbs(
                prompt_title or f"Run: {recipe_title}",
                root_title=root_breadcrumb,
                published_title=published_title,
            )
        case _:
            raise ValueError(f"Unknown tab: {tab}")
