from __future__ import annotations

import pydantic


class NavWorkflowItem(pydantic.BaseModel):
    title: str
    href: str
    image_url: str | None = None
    icon: str | None = None  # FA class fallback when no image


class NavItemData(pydantic.BaseModel):
    key: str
    label: str
    icon: str  # HTML <i> element (rendered as raw HTML), e.g. icons.home
    href: str
    items: list[NavWorkflowItem] = []  # nested children, e.g. saved workflows
    collapsible: bool = True  # False keeps `items` always expanded (no chevron)


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


class NavAccountData(pydantic.BaseModel):
    user: NavUserData | None = None  # None => anonymous
    current_workspace: WorkspaceData | None = None
    workspaces: list[WorkspaceData] = []
    menu_links: list[MenuLinkData] = []
    logout_href: str = ""
    add_workspace_url: str = ""
    login_href: str = "/login/"
    enable_firebase_auth: bool = False


class NavigationSidebarProps(pydantic.BaseModel):
    _component: str = "NavigationSidebar"

    logo_image_url: str
    nav_items: list[NavItemData] = []
    active_key: str | None = None
    account: NavAccountData = pydantic.Field(default_factory=NavAccountData)
    gooey_builder: GooeyBuilderData | None = None
    default_collapsed: bool = False
