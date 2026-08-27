from __future__ import annotations

from fastapi import HTTPException

from app_users.models import AppUser
from bots.models import SavedRun
from daras_ai_v2 import icons

DEFAULT_SURFACE = SavedRun.Surface.run


# The order the tabs read in, which is roughly how often a workspace looks at
# them - their own runs first, their deployed copilots next - rather than the
# order the enum happens to be declared in.
SURFACE_ORDER: list[SavedRun.Surface] = [
    SavedRun.Surface.run,
    SavedRun.Surface.deployment,
    SavedRun.Surface.builder_child,
    SavedRun.Surface.tool_call,
    SavedRun.Surface.api,
    SavedRun.Surface.analysis,
    SavedRun.Surface.bulk,
    SavedRun.Surface.export,
    # admin-only, so they sit after everything a workspace can see
    SavedRun.Surface.builder_prompt,
    SavedRun.Surface.internal,
]

# `Surface.label` names the thing that made the run ("Deployment"); a tab names
# what you'll find under it ("Deployed Chats"), so these read as plurals.
SURFACE_LABELS: dict[SavedRun.Surface, str] = {
    SavedRun.Surface.run: "Runs",
    SavedRun.Surface.deployment: "Deployed Chats",
    SavedRun.Surface.builder_child: "Ask Gooey",
    SavedRun.Surface.tool_call: "Tools",
    SavedRun.Surface.api: "API",
    SavedRun.Surface.analysis: "Analysis",
    SavedRun.Surface.bulk: "Bulk",
    SavedRun.Surface.export: "Exports",
    SavedRun.Surface.builder_prompt: "Ask Prompt",
    SavedRun.Surface.internal: "Internal",
}

# Borrowed from wherever the app already draws these: the Run tab's runner, the
# Deploy tab's four-platform strip, the API tab's rocket, and the Bulk Runner
# and Functions workflows' own emoji.
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
    if user and user.is_admin():
        return list(SURFACE_ORDER)
    return [s for s in SURFACE_ORDER if s not in ADMIN_ONLY_SURFACES]
