import typing


from bots.models import SavedRun, PublishedRun

if typing.TYPE_CHECKING:
    from routers.root import RecipeTabs
    from daras_ai_v2.base import BasePage


class TitleUrl(typing.NamedTuple):
    title: str
    url: str


class TitleBreadCrumbs(typing.NamedTuple):
    """
    Render Syntax: [root_title](root_url) / h1_prefx: [h1_title](h1_url)
    """

    root_title: TitleUrl | None = None
    h1_prefix: str | None = None
    h1_title: TitleUrl | None = None

    def has_breadcrumbs(self):
        return bool(self.root_title)

    def title_with_prefix(self) -> str:
        if not self.h1_title.title:
            return ""
        ret = ""
        if self.h1_prefix:
            ret = self.h1_prefix + ": "
        ret += self.h1_title.title
        return ret

    def title_with_prefix_url(self) -> str:
        if not self.h1_title.title:
            return ""
        ret = ""
        if self.h1_prefix:
            ret = self.h1_prefix + ": "
        if self.h1_title.url:
            ret += f"[{self.h1_title.title}]({self.h1_title.url})"
        else:
            ret += self.h1_title.title
        return ret


def get_title_breadcrumbs(
    page_cls: typing.Union["BasePage", typing.Type["BasePage"]],
    sr: SavedRun,
    pr: PublishedRun | None,
    tab: typing.Optional["RecipeTabs"] = None,
) -> TitleBreadCrumbs:
    from routers.root import RecipeTabs

    is_root = pr and pr.saved_run == sr and pr.is_root()
    is_example = not is_root and pr and pr.saved_run == sr
    is_run = not is_root and not is_example
    is_api_call = sr.is_api_call and tab == RecipeTabs.run

    metadata = page_cls.workflow.get_or_create_metadata()
    root_title = TitleUrl(
        f"{metadata.emoji} {metadata.short_title}", page_cls.app_url()
    )

    match tab:
        case RecipeTabs.examples | RecipeTabs.history | RecipeTabs.saved:
            return TitleBreadCrumbs(
                root_title=root_title,
                h1_prefix=tab.label,
                h1_title=TitleUrl(metadata.short_title, root_title.url),
            )
        case _ if is_root:
            return TitleBreadCrumbs(
                h1_prefix=tab.label if tab else "",
                h1_title=TitleUrl(
                    page_cls.get_recipe_title(),
                    root_title.url if tab != RecipeTabs.run else "",
                ),
            )
        case _ if is_example:
            assert pr is not None
            return TitleBreadCrumbs(
                root_title=root_title,
                h1_prefix=tab.label if tab else "",
                h1_title=TitleUrl(
                    (
                        pr.title
                        or page_cls.get_prompt_title(sr)
                        or page_cls.get_run_title(sr, pr)
                    ),
                    pr.get_app_url() if tab != RecipeTabs.run else "",
                ),
            )
        case _ if is_run:
            if tab and tab.label:
                prefix = tab.label
            elif is_api_call:
                prefix = "API Run"
            else:
                prefix = "Run"

            prompt_title = page_cls.get_prompt_title(sr)
            if pr and not pr.is_root():
                h1_title = TitleUrl(
                    title=prompt_title or pr.title or f"Fork: {pr.published_run_id}",
                    url=pr and pr.get_app_url(),
                )
            else:
                h1_title = TitleUrl(
                    title=prompt_title or page_cls.get_run_title(sr, pr),
                    url=root_title.url,
                )

            return TitleBreadCrumbs(
                root_title=root_title, h1_prefix=prefix, h1_title=h1_title
            )
        case _:
            raise ValueError(f"Unknown tab: {tab}")
