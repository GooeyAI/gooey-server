from daras_ai_v2 import settings


def can_use_layout_v2(page_slug: str) -> bool:
    """Whether this recipe renders in layout v2.

    Scoped to the recipes actually forked to v2, so turning v2 on for a recipe means adding
    it to `all_pages_v2` rather than flipping anything here: one with no fork keeps its v1
    page and its v1 tabs. Taking the slug rather than the request is what makes that
    scoping structural - a caller cannot ask the question without saying which recipe.

    Deliberately not request-dependent. Anonymous visitors get v2 too, so the answer is the
    same for everyone and a response no longer varies by who is asking.
    """
    from daras_ai_v2.all_pages import normalize_slug
    from daras_ai_v2.all_pages_v2 import page_slug_map_v2

    if not settings.ENABLE_LAYOUT_V2:
        return False
    return normalize_slug(page_slug) in page_slug_map_v2
