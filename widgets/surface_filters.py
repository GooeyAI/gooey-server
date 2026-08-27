from __future__ import annotations

from fastapi import HTTPException

from app_users.models import AppUser
from bots.models import SavedRun
from daras_ai_v2 import icons

DEFAULT_SURFACE = SavedRun.Surface.run


# Tab order: roughly how often a workspace looks at each, rather than the order
# the enum happens to declare. A surface missing here sorts to the end, so a new
# one shows up rather than vanishing.
SURFACE_ORDER: list[SavedRun.Surface] = [
    SavedRun.Surface.run,
    SavedRun.Surface.deployment,
    SavedRun.Surface.builder_child,
    SavedRun.Surface.tool_call,
    SavedRun.Surface.api,
    SavedRun.Surface.analysis,
    SavedRun.Surface.bulk,
    SavedRun.Surface.export,
]

# `Surface.label` names what made the run ("Deployment"); a tab names what you
# find under it. Only the ones that actually differ - the rest fall through.
SURFACE_LABELS: dict[SavedRun.Surface, str] = {
    SavedRun.Surface.run: "Runs",
    SavedRun.Surface.deployment: "Deployed Chats",
    SavedRun.Surface.builder_child: "Ask Gooey",
    SavedRun.Surface.tool_call: "Tools",
    SavedRun.Surface.export: "Exports",
}

# Borrowed from wherever the app already draws these: the Run tab's runner, the
# Deploy tab's four-platform strip, the API tab's rocket, and the Bulk Runner and
# Functions workflows' own emoji.
SURFACE_ICONS: dict[SavedRun.Surface, str] = {
    SavedRun.Surface.run: icons.run,
    SavedRun.Surface.deployment: (
        f'<img width="16" height="16" style="margin-top: -3px"'
        f' src="{icons.integrations_img}" alt="Deployed">'
    ),
    SavedRun.Surface.builder_child: icons.sparkles,
    SavedRun.Surface.tool_call: "🛠️",
    SavedRun.Surface.api: icons.api,
    SavedRun.Surface.analysis: '<i class="fa-regular fa-chart-line"></i>',
    SavedRun.Surface.bulk: "🦾",
    SavedRun.Surface.export: icons.download_solid,
    SavedRun.Surface.builder_prompt: icons.sparkles,
    SavedRun.Surface.internal: icons.code,
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


def surface_label(surface: SavedRun.Surface) -> str:
    return SURFACE_LABELS.get(surface) or surface.label


def visible_surfaces(user: AppUser | None) -> list[SavedRun.Surface]:
    surfaces = sorted(SavedRun.Surface, key=_tab_position)
    if user and user.is_admin():
        return surfaces
    return [s for s in surfaces if s not in ADMIN_ONLY_SURFACES]


def _tab_position(surface: SavedRun.Surface) -> int:
    try:
        return SURFACE_ORDER.index(surface)
    except ValueError:
        return len(SURFACE_ORDER)
