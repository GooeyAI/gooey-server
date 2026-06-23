from __future__ import annotations

import pydantic


class NavItemData(pydantic.BaseModel):
    key: str
    label: str
    icon: str  # FontAwesome class, e.g. "fa-regular fa-house"
    href: str


class NavWorkflowData(pydantic.BaseModel):
    title: str
    href: str
    image_url: str | None = None
    icon: str | None = None  # FA class fallback when no image


class WorkspaceData(pydantic.BaseModel):
    id: int
    name: str
    icon_html: str  # workspace.html_icon()
    is_current: bool = False


class MenuLinkData(pydantic.BaseModel):
    label: str
    href: str
    icon: str | None = None  # FA class


class NavUserData(pydantic.BaseModel):
    name: str
    initial: str
    photo_url: str | None = None


class GooeyBuilderData(pydantic.BaseModel):
    photo_url: str


class NavigationSidebarProps(pydantic.BaseModel):
    _component: str = "NavigationSidebar"

    # primary nav (Task 1)
    logo_image_url: str
    nav_items: list[NavItemData] = []
    active_key: str | None = None
    new_href: str

    # workflow lists (Task 3)
    saved_href: str = ""
    saved_workflows: list[NavWorkflowData] = []
    recent_workflows: list[NavWorkflowData] = []

    # identity / workspace / menu (Task 4) + anonymous (Task 5)
    user: NavUserData | None = None  # None => anonymous
    current_workspace: WorkspaceData | None = None
    workspaces: list[WorkspaceData] = []
    menu_links: list[MenuLinkData] = []
    logout_href: str = ""
    switch_workspace_href: str = ""  # POST/GET target, {workspace_id} templated by React
    login_href: str = "/login/"

    # gooey builder (Task 7)
    gooey_builder: GooeyBuilderData | None = None

    # collapse (Task 2)
    default_collapsed: bool = False
