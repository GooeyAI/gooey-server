import fastapi

from daras_ai_v2 import settings


def can_use_layout_v2(request: fastapi.Request) -> bool:
    if not settings.ENABLE_LAYOUT_V2:
        return False
    if not request.user or request.user.is_anonymous:
        return False
    # Initial rollout is admin-only.
    return request.user.is_admin()
