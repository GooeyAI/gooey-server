from __future__ import annotations

import typing

import pydantic

# One-shot instruction handed to the client as navigation state (never as a url
# fragment), so it applies to the navigation it was issued for and is forgotten
# afterwards. There is deliberately no "close": the Builder panel stays open
# until the user closes it.
BuilderIntent = typing.Literal["open"]


class NavWorkflowItem(pydantic.BaseModel):
    title: str
    href: str
    image_url: str | None = None  # published run photo, preferred over `icon`
    icon: str | None = None  # FontAwesome icon HTML, or a bare emoji
    builder_intent: BuilderIntent | None = None


class NavItemData(pydantic.BaseModel):
    key: str  # stable identity matched against NavigationSidebarProps.active_key
    label: str
    icon: str  # HTML <i> element (rendered as raw HTML), e.g. icons.home
    href: str | None = None
    items: list[NavWorkflowItem] = []  # nested children, e.g. saved workflows
    # Endpoint to load `items` from after the page renders, keeping a slow query
    # off the SSR path. The section hides itself if the response is empty.
    items_url: str | None = None
    # Scopes the client-side cache of `items_url` results, so one browser tab
    # never shows another user's or workspace's rows.
    items_cache_key: str | None = None
    collapsible: bool = True  # False keeps `items` always expanded (no chevron)
    dense: bool = False  # True means less spacing and smaller font


class WorkspaceData(pydantic.BaseModel):
    id: int
    name: str
    icon_html: str  # workspace.html_icon()
    subtitle: str = ""  # e.g. "Personal" or "Org · 12 members"
    is_current: bool = False
    is_personal: bool = False


class MenuLinkData(pydantic.BaseModel):
    label: str
    href: str
    icon: str | None = None  # FA class


class NavUserData(pydantic.BaseModel):
    name: str
    photo_url: str | None = None


class GooeyBuilderData(pydantic.BaseModel):
    photo_url: str
    name: str
    event_key: str
    storage_key: str | None = None
    # Where to go before opening, for a page that cannot hold the panel: Deploy, API and
    # Usage offer the way in but have no workspace beside it, so the rail navigates to the
    # workspace and the panel opens on arrival. None where the page holds it already.
    open_href: str | None = None


class NavAccountData(pydantic.BaseModel):
    user: NavUserData | None = None  # None => anonymous
    current_workspace: WorkspaceData | None = None
    workspaces: list[WorkspaceData] = []
    switch_workspace_key: str | None = None
    menu_links: list[MenuLinkData] = []
    logout_href: str = ""
    add_workspace_url: str = ""
    login_href: str = "/login/"
    enable_firebase_auth: bool = False


class NavigationSidebarProps(pydantic.BaseModel):
    _component: str = "NavigationSidebar"

    logo_image_url: str
    logo_href: str
    nav_items: list[NavItemData] = []
    active_key: str | None = None
    collapsed_state_key: str
    account: NavAccountData = pydantic.Field(default_factory=NavAccountData)
    gooey_builder: GooeyBuilderData | None = None
    default_collapsed: bool = False
