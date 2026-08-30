import typing

from daras_ai_v2.all_pages import normalize_slug
from daras_ai_v2.base_v2 import BasePage
from recipes.VideoBots_v2 import VideoBotsPageV2

# recipes forked to layout v2 so far (grows one at a time as recipes migrate)
all_pages_v2: list[typing.Type[BasePage]] = [
    VideoBotsPageV2,
]

page_slug_map_v2: dict[str, typing.Type[BasePage]] = {
    normalize_slug(slug): page for page in all_pages_v2 for slug in page.slug_versions
}
