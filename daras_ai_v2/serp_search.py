import typing

import requests

from daras_ai_v2 import settings
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
    links = [
        SerpLink(
            url=url,
            title=item.get("title") or "",
            snippet=item.get("snippet") or "",
        )
        for item in items
        if (url := item.get("link") or item.get("website"))
    ]
    return data, links


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
    r.raise_for_status()
    data = r.json()
    return data
