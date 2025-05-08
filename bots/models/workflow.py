from __future__ import annotations

import typing

from django.db import models

from app_users.models import AppUser
from bots.custom_fields import CustomURLField
from daras_ai_v2 import icons, urls
from daras_ai_v2.fastapi_tricks import get_route_path
from gooeysite.custom_create import get_or_create_lazy
from workspaces.models import Workspace

if typing.TYPE_CHECKING:
    from daras_ai_v2.base import BasePage

    from .published_run import PublishedRun


class WorkflowAccessLevel(models.IntegerChoices):
    VIEW_ONLY = 1
    FIND_AND_VIEW = 2
    EDIT = 4

    # migration: set pr.public_access=VIEW_ONLY, pr.workspace_access=EDIT
    INTERNAL = (3, "Internal (Deprecated)")

    @classmethod
    def get_team_sharing_options(
        cls, pr: PublishedRun, current_user: "AppUser"
    ) -> typing.List[WorkflowAccessLevel]:
        if not cls.can_user_delete_published_run(
            workspace=pr.workspace,
            user=current_user,
            pr=pr,
        ):
            options = [WorkflowAccessLevel(pr.workspace_access)]
        elif pr.workspace.can_have_private_published_runs():
            options = [cls.VIEW_ONLY, cls.FIND_AND_VIEW, cls.EDIT]
        else:
            options = [cls.FIND_AND_VIEW, cls.EDIT]

        if (perm := WorkflowAccessLevel(pr.workspace_access)) not in options:
            options.append(perm)
        return options

    @classmethod
    def get_public_sharing_options(
        cls, pr: PublishedRun
    ) -> typing.List[WorkflowAccessLevel]:
        if pr.workspace.can_have_private_published_runs():
            options = [cls.VIEW_ONLY, cls.FIND_AND_VIEW]
        else:
            options = [cls.FIND_AND_VIEW]

        if (perm := WorkflowAccessLevel(pr.public_access)) not in options:
            options.append(perm)
        return options

    def get_team_sharing_icon(self) -> str:
        match self:
            case WorkflowAccessLevel.VIEW_ONLY:
                return icons.eye_slash
            case WorkflowAccessLevel.FIND_AND_VIEW:
                return icons.eye
            case WorkflowAccessLevel.EDIT:
                return icons.company_solid
            case _:
                raise ValueError("Invalid permission for team sharing")

    def get_public_sharing_icon(self):
        match self:
            case WorkflowAccessLevel.VIEW_ONLY | WorkflowAccessLevel.INTERNAL:
                return icons.eye_slash
            case WorkflowAccessLevel.FIND_AND_VIEW:
                return icons.globe
            case _:
                raise ValueError("Invalid permission for public sharing")

    def get_team_sharing_label(self):
        match self:
            case WorkflowAccessLevel.VIEW_ONLY:
                return "Private"
            case WorkflowAccessLevel.FIND_AND_VIEW:
                return "View Only"
            case WorkflowAccessLevel.EDIT:
                return "Editable"
            case _:
                raise ValueError("Invalid permission for team sharing")

    def get_public_sharing_label(self):
        match self:
            case WorkflowAccessLevel.VIEW_ONLY | WorkflowAccessLevel.INTERNAL:
                return "Unlisted"
            case WorkflowAccessLevel.FIND_AND_VIEW:
                return "Public"
            case _:
                raise ValueError("Invalid permission for public sharing")

    def get_team_sharing_text(self, pr: PublishedRun, current_user: "AppUser"):
        from routers.account import saved_route

        match self:
            case WorkflowAccessLevel.VIEW_ONLY:
                if pr.created_by_id == current_user.id:
                    members_text = "you and members"
                else:
                    members_text = "members"
                text = f": Only {members_text} with a link can view."
            case WorkflowAccessLevel.FIND_AND_VIEW:
                if self.can_user_delete_published_run(
                    workspace=pr.workspace, user=current_user, pr=pr
                ):
                    text = f": Members [can find]({get_route_path(saved_route)}) but can't update."
                else:
                    text = (
                        f": Members [can find]({get_route_path(saved_route)}) and view."
                    )
                    if pr.created_by_id:
                        text += f"<br/>{pr.created_by.full_name()} + admins can update."
                    else:
                        text += "<br/>Admins can update."
            case WorkflowAccessLevel.EDIT:
                text = f": Members [can find]({get_route_path(saved_route)}) and edit."
            case _:
                raise ValueError("Invalid permission for team sharing")

        icon, label = self.get_team_sharing_icon(), self.get_team_sharing_label()
        return f"{icon} **{label}**{text}"

    def get_public_sharing_text(self, pr: PublishedRun) -> str:
        from routers.account import profile_route

        match self:
            case WorkflowAccessLevel.VIEW_ONLY | WorkflowAccessLevel.INTERNAL:
                text = ": Only people with a link can view"
            case WorkflowAccessLevel.FIND_AND_VIEW:
                profile_url = (
                    pr.workspace.handle_id and pr.workspace.handle.get_app_url()
                )
                if profile_url:
                    pretty_url = urls.remove_scheme(profile_url).rstrip("/")
                    text = f" on [{pretty_url}]({profile_url}) (view only)"
                else:
                    text = f" on [your profile page]({get_route_path(profile_route)})"
            case WorkflowAccessLevel.EDIT:
                raise ValueError("Invalid permission for public sharing")

        icon, label = self.get_public_sharing_icon(), self.get_public_sharing_label()
        return f"{icon} **{label}**" + text

    @classmethod
    def can_user_delete_published_run(
        cls, *, workspace: Workspace, user: AppUser, pr: PublishedRun
    ) -> bool:
        if pr.is_root():
            return False
        if user.is_admin():
            return True
        return bool(
            user
            and workspace.id == pr.workspace_id
            and (
                pr.created_by_id == user.id
                or pr.workspace.get_admins().filter(id=user.id).exists()
            )
        )

    @classmethod
    def can_user_edit_published_run(
        cls, *, workspace: Workspace, user: AppUser, pr: PublishedRun
    ) -> bool:
        if user.is_admin():
            return True
        return bool(
            user
            and workspace.id == pr.workspace_id
            and (
                (
                    pr.workspace_access == WorkflowAccessLevel.EDIT
                    and pr.workspace.memberships.filter(user=user).exists()
                )
                or pr.created_by_id == user.id
                or pr.workspace.get_admins().filter(id=user.id).exists()
            )
        )


class Workflow(models.IntegerChoices):
    DOC_SEARCH = (1, "Doc Search")
    DOC_SUMMARY = (2, "Doc Summary")
    GOOGLE_GPT = (3, "Google GPT")
    VIDEO_BOTS = (4, "Copilot")
    LIPSYNC_TTS = (5, "Lipysnc + TTS")
    TEXT_TO_SPEECH = (6, "Text to Speech")
    ASR = (7, "Speech Recognition")
    LIPSYNC = (8, "Lipsync")
    DEFORUM_SD = (9, "Deforum Animation")
    COMPARE_TEXT2IMG = (10, "Compare Text2Img")
    TEXT_2_AUDIO = (11, "Text2Audio")
    IMG_2_IMG = (12, "Img2Img")
    FACE_INPAINTING = (13, "Face Inpainting")
    GOOGLE_IMAGE_GEN = (14, "Google Image Gen")
    COMPARE_UPSCALER = (15, "Compare AI Upscalers")
    SEO_SUMMARY = (16, "SEO Summary")
    EMAIL_FACE_INPAINTING = (17, "Email Face Inpainting")
    SOCIAL_LOOKUP_EMAIL = (18, "Social Lookup Email")
    OBJECT_INPAINTING = (19, "Object Inpainting")
    IMAGE_SEGMENTATION = (20, "Image Segmentation")
    COMPARE_LLM = (21, "Compare LLM")
    CHYRON_PLANT = (22, "Chyron Plant")
    LETTER_WRITER = (23, "Letter Writer")
    SMART_GPT = (24, "Smart GPT")
    QR_CODE = (25, "AI QR Code")
    DOC_EXTRACT = (26, "Doc Extract")
    RELATED_QNA_MAKER = (27, "Related QnA Maker")
    RELATED_QNA_MAKER_DOC = (28, "Related QnA Maker Doc")
    EMBEDDINGS = (29, "Embeddings")
    BULK_RUNNER = (30, "Bulk Runner")
    BULK_EVAL = (31, "Bulk Evaluator")
    FUNCTIONS = (32, "Functions")
    TRANSLATION = (33, "Translation")
    MODEL_TRAINER = (34, "Model Trainer")

    @property
    def short_slug(self):
        return min(self.page_cls.slug_versions, key=len)

    @property
    def short_title(self):
        metadata = self.get_or_create_metadata()
        return metadata.short_title

    @property
    def emoji(self):
        metadata = self.get_or_create_metadata()
        return metadata.emoji

    @property
    def page_cls(self) -> typing.Type[BasePage]:
        from daras_ai_v2.all_pages import workflow_map

        return workflow_map[self]

    def get_or_create_metadata(self) -> "WorkflowMetadata":
        return get_or_create_lazy(
            WorkflowMetadata,
            workflow=self,
            create=lambda **kwargs: WorkflowMetadata.objects.create(
                **kwargs,
                short_title=(self.page_cls.get_root_pr().title or self.page_cls.title),
                default_image=self.page_cls.explore_image or "",
                meta_title=(self.page_cls.get_root_pr().title or self.page_cls.title),
                meta_description=self.page_cls.get_root_pr().notes,
                meta_image=self.page_cls.explore_image or "",
            ),
        )[0]


class WorkflowMetadata(models.Model):
    workflow = models.IntegerField(choices=Workflow.choices, unique=True)

    short_title = models.TextField(help_text="Title used in breadcrumbs")
    default_image = models.URLField(
        blank=True, default="", help_text="Image shown on explore page"
    )

    meta_title = models.TextField()
    meta_description = models.TextField(blank=True, default="")
    meta_image = CustomURLField(default="", blank=True)

    meta_keywords = models.JSONField(
        default=list, blank=True, help_text="(Not implemented)"
    )
    help_url = models.URLField(blank=True, default="", help_text="(Not implemented)")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    price_multiplier = models.FloatField(default=1)
    emoji = models.TextField(blank=True, default="")

    def __str__(self):
        return self.meta_title
