import typing

import requests

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.serp_search_locations import SerpSearchType, SerpSearchLocation


class SerpLink(typing.NamedTuple):
    url: str
    title: str
    snippet: str


def get_related_questions_from_serp_api(
    search_query: str,
    *,
    search_location: SerpSearchLocation,
) -> tuple[dict, list[str]]:
    data = call_serp_api(
        search_query,
        search_type=SerpSearchType.SEARCH,
        search_location=search_location,
    )
    items = data.get("peopleAlsoAsk", []) or data.get("relatedSearches", [])
    related_questions = [
        q for item in items if (q := item.get("question") or item.get("query"))
    ]
    return data, related_questions


def get_links_from_serp_api(
    query: str,
    *,
    search_type: SerpSearchType,
    search_location: SerpSearchLocation,
) -> tuple[dict, list[SerpLink]]:
    data = call_serp_api(
        query, search_type=search_type, search_location=search_location
    )
    items = (
        data.get("organic")
        or data.get("images")
        or data.get("videos")
        or data.get("places")
        or data.get("news")
        or []
    )
    links = list(filter(None, map(item_to_serp_link, items)))
    return data, links


def item_to_serp_link(item: dict | None) -> SerpLink | None:
    if not item:
        return None
    url = item.get("link") or item.get("website")
    if not url:
        return None

    snippet = item.get("snippet") or ""

    image_url = item.get("imageUrl")
    if image_url and image_url.startswith("http"):
        snippet = f"Image URL: {image_url}\n\n{snippet}".strip()
    thumbnail_url = item.get("thumbnailUrl")
    if thumbnail_url and thumbnail_url.startswith("http"):
        snippet = f"Thumbnail URL: {thumbnail_url}\n\n{snippet}".strip()

    return SerpLink(url=url, title=item.get("title") or "", snippet=snippet)


def call_serp_api(
    query: str,
    *,
    search_type: SerpSearchType,
    search_location: SerpSearchLocation,
) -> dict:
    r = requests.post(
        "https://google.serper.dev/" + search_type.value,
        json=dict(
            q=query,
            gl=search_location.value,
        ),
        headers={"X-API-KEY": settings.SERPER_API_KEY},
    )
    raise_for_status(r)
    data = r.json()
    return data
