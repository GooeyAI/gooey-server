from __future__ import annotations

from typing import Annotated, Literal

import pydantic


class ChatPreview(pydantic.BaseModel):
    type: Literal["chat"] = "chat"
    user_message: str | None = None
    bot_message: str | None = None


class MediaPreview(pydantic.BaseModel):
    type: Literal["image", "video", "audio"]
    url: str
    preview_img: str | None = None
    caption: str | None = None


class IconPreview(pydantic.BaseModel):
    type: Literal["icon"] = "icon"
    image_url: str | None = None
    icon: str | None = None


CardPreview = Annotated[
    ChatPreview | MediaPreview | IconPreview, pydantic.Field(discriminator="type")
]


class AccessBadgeData(pydantic.BaseModel):
    icon_html: str
    label: str


class AuthorData(pydantic.BaseModel):
    name: str
    photo_url: str | None = None


class RunStatusData(pydantic.BaseModel):
    state: Literal["starting", "running", "failed", "cancelled"]
    label: str


class SenderData(pydantic.BaseModel):
    """Who a deployment run was for, as opposed to who owns the integration."""

    icon: str
    label: str


class WorkflowCardData(pydantic.BaseModel):
    title: str
    href: str
    workflow_icon: str | None = None
    description: str | None = None
    author: AuthorData | None = None
    # shown in the author's place: a deployment run's author is the integration's
    # owner, not whoever sent the message
    sender: SenderData | None = None
    run_status: RunStatusData | None = None
    preview: CardPreview | None = None
    updated_at: str | None = None
    run_count: int | None = None
    access_badge: AccessBadgeData | None = None
    change_notes: str | None = None


class WorkflowTabData(pydantic.BaseModel):
    id: int
    title: str
    icon: str
    cards: list[WorkflowCardData]


class WorkspaceHeaderData(pydantic.BaseModel):
    name: str
    photo_url: str
    description: str | None = None
    settings_href: str | None = None


class IndustryTileData(pydantic.BaseModel):
    id: int
    name: str
    icon: str
    color: str | None = None
    description: str
    workflow_count: int
    href: str


class NewsItemData(pydantic.BaseModel):
    id: int
    headline: str
    tag: str
    photo_url: str | None = None
    publish_date: str
    href: str


class HomePageProps(pydantic.BaseModel):
    _component: str = "HomePage"

    greeting: str | None = None
    workspace_header: WorkspaceHeaderData | None = None
    recent_workflows: list[WorkflowCardData] = []
    recent_workflows_href: str = ""
    saved_workflows: list[WorkflowCardData] = []
    saved_workflows_href: str = ""
    workflow_tabs: list[WorkflowTabData] = []
    industry_tiles: list[IndustryTileData] = []
    news_items: list[NewsItemData] = []
