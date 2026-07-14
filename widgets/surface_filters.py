from __future__ import annotations

from fastapi import HTTPException

from app_users.models import AppUser
from bots.models import SavedRun
from daras_ai_v2 import icons

DEFAULT_SURFACE = SavedRun.Surface.run


SURFACE_ICONS: dict[SavedRun.Surface, str] = {
    SavedRun.Surface.run: icons.run,
    SavedRun.Surface.api: icons.api,
    SavedRun.Surface.deployment: icons.chat,
    SavedRun.Surface.builder_child: icons.sparkles,
    SavedRun.Surface.tool_call: icons.code,
    SavedRun.Surface.analysis: icons.search,
    SavedRun.Surface.export: icons.download_solid,
    SavedRun.Surface.bulk: icons.library,
}


# surfaces only shown to (and accessible by) Gooey admins
ADMIN_ONLY_SURFACES: set[SavedRun.Surface] = {
    SavedRun.Surface.builder_prompt,
    SavedRun.Surface.internal,
}


def parse_surface(slug: str | None) -> SavedRun.Surface:
    if not slug:
        return DEFAULT_SURFACE
    try:
        return SavedRun.Surface[slug]
    except KeyError:
        raise HTTPException(status_code=404)


def visible_surfaces(user: AppUser | None) -> list[SavedRun.Surface]:
    if user and user.is_admin():
        return list(SavedRun.Surface)
    return [s for s in SavedRun.Surface if s not in ADMIN_ONLY_SURFACES]
