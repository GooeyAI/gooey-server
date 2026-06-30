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
    icon: str  # FontAwesome class, e.g. "fa-regular fa-house"
    href: str
    items: list[NavWorkflowItem] = []  # nested children, e.g. saved workflows


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


class NavAccountData(pydantic.BaseModel):
    user: NavUserData | None = None  # None => anonymous
    current_workspace: WorkspaceData | None = None
    workspaces: list[WorkspaceData] = []
    menu_links: list[MenuLinkData] = []
    logout_href: str = ""
    # JS onClick handler string (workspaces.widgets.open_create_workspace_popup_js),
    # run client-side like a server-rendered onClick — not a plain URL.
    add_workspace_onclick: str = ""
    login_href: str = "/login/"


class NavigationSidebarProps(pydantic.BaseModel):
    _component: str = "NavigationSidebar"

    logo_image_url: str
    nav_items: list[NavItemData] = []
    active_key: str | None = None
    recent_workflows: list[NavWorkflowItem] = []
    account: NavAccountData = pydantic.Field(default_factory=NavAccountData)
    gooey_builder: GooeyBuilderData | None = None
    default_collapsed: bool = False
