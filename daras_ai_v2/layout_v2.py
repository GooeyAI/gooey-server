import fastapi

from daras_ai_v2 import settings


def can_use_layout_v2(request: fastapi.Request) -> bool:
    if not settings.ENABLE_LAYOUT_V2:
        return False
    if not request.user or request.user.is_anonymous:
        return False
    # deliberately admin-only for now (no per-workspace opt-in arm yet, unlike
    # can_launch_gooey_builder's workspace arm) - a workspace flag is a future addition,
    # not an oversight.
    return request.user.is_admin()
