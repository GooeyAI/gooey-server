from __future__ import annotations

import datetime
import typing
from collections import defaultdict
from multiprocessing.pool import ThreadPool

import phonenumber_field.formfields
import phonenumber_field.modelfields
import pytz
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q, IntegerChoices, QuerySet, Subquery, OuterRef
from django.utils import timezone
from django.utils.text import Truncator

from app_users.models import AppUser
from bots.admin_links import open_in_new_tab
from bots.custom_fields import PostgresJSONEncoder, CustomURLField
from daras_ai_v2 import icons, urls
from daras_ai_v2.crypto import get_random_doc_id
from daras_ai_v2.fastapi_tricks import get_route_path, get_api_route_url
from daras_ai_v2.language_model import format_chat_entry
from functions.models import CalledFunctionResponse
from gooeysite.bg_db_conn import get_celery_result_db_safe
from gooeysite.custom_create import get_or_create_lazy
from workspaces.models import WorkspaceMembership

if typing.TYPE_CHECKING:
    import celery.result
    from daras_ai_v2.base import BasePage
    from workspaces.models import Workspace

CHATML_ROLE_USER = "user"
CHATML_ROLE_ASSISSTANT = "assistant"

EPOCH = datetime.datetime.utcfromtimestamp(0)


class WorkflowAccessLevel(models.IntegerChoices):
    VIEW_ONLY = 1
    FIND_AND_VIEW = 2
    EDIT = 4

    # migration: set pr.public_access=VIEW_ONLY, pr.workspace_access=EDIT
    INTERNAL = (3, "Internal (Deprecated)")

    @classmethod
    def get_team_sharing_options(
        cls, pr: "PublishedRun", current_user: "AppUser"
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
        cls, pr: "PublishedRun"
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
                return "Unlisted"
            case WorkflowAccessLevel.FIND_AND_VIEW:
                return "Visible"
            case WorkflowAccessLevel.EDIT:
                return "Edit"
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

    def get_team_sharing_text(self, pr: "PublishedRun", current_user: "AppUser"):
        from routers.account import saved_route

        match self:
            case WorkflowAccessLevel.VIEW_ONLY:
                text = ": Only members with a link can view"
            case WorkflowAccessLevel.FIND_AND_VIEW:
                if self.can_user_delete_published_run(
                    workspace=pr.workspace,
                    user=current_user,
                    pr=pr,
                ):
                    text = f": Members [can find]({get_route_path(saved_route)}) but can't update"
                else:
                    text = (
                        f": Members [can find]({get_route_path(saved_route)}) and view."
                    )
                    if pr.created_by_id:
                        text += f"<br/>{pr.created_by.full_name()} + admins can update."
                    else:
                        text += "<br/>Admins can update."
            case WorkflowAccessLevel.EDIT:
                text = f": Members [can find]({get_route_path(saved_route)}) and edit"
            case _:
                raise ValueError("Invalid permission for team sharing")

        icon, label = self.get_team_sharing_icon(), self.get_team_sharing_label()
        return f"{icon} **{label}**" + text

    def get_public_sharing_text(self, pr: "PublishedRun") -> str:
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


class Platform(models.IntegerChoices):
    FACEBOOK = (1, "Facebook Messenger")
    INSTAGRAM = (2, "Instagram")
    WHATSAPP = (3, "WhatsApp")
    SLACK = (4, "Slack")
    WEB = (5, "Web")
    TWILIO = (6, "Twilio")

    def get_icon(self):
        match self:
            case Platform.WEB:
                return icons.globe
            case Platform.TWILIO:
                return '<img src="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/73d11836-3988-11ef-9e06-02420a00011a/favicon-32x32.png" style="height: 1.2em; vertical-align: middle;">'
            case _:
                return f'<i class="fa-brands fa-{self.name.lower()}"></i>'


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
    MODEL_TRAINER = (34, "Translation")

    @property
    def short_slug(self):
        return min(self.page_cls.slug_versions, key=len)

    @property
    def short_title(self):
        metadata = self.get_or_create_metadata()
        return metadata.short_title

    @property
    def page_cls(self) -> typing.Type["BasePage"]:
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
                meta_description=(
                    self.page_cls().preview_description(state={})
                    or self.page_cls.get_root_pr().notes
                ),
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


class SavedRunQuerySet(models.QuerySet):
    def to_df(self, tz=pytz.timezone(settings.TIME_ZONE)) -> "pd.DataFrame":
        import pandas as pd

        # export only the first 10,000 records
        qs = self.all()[:10_000]
        # Convert the queryset to a list of dicts
        records = [sr.to_dict() | {"web_url": sr.get_app_url()} for sr in qs]
        # Convert the list of dicts to a dataframe
        df = pd.DataFrame.from_records(records)
        # Identify datetime columns and convert them to the specified timezone
        for column, dtype in df.dtypes.items():
            if not pd.api.types.is_datetime64_any_dtype(dtype):
                continue
            df[column] = df[column].dt.tz_convert(tz)
        return df


class RetentionPolicy(IntegerChoices):
    keep = 0, "Keep"
    delete = 1, "Delete"


class SavedRun(models.Model):
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    parent_version = models.ForeignKey(
        "bots.PublishedRunVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children_runs",
    )

    workflow = models.IntegerField(
        choices=Workflow.choices, default=Workflow.VIDEO_BOTS
    )
    run_id = models.CharField(max_length=128, default=None, null=True, blank=True)
    uid = models.CharField(max_length=128, default=None, null=True, blank=True)
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.SET_NULL,
        related_name="saved_runs",
        null=True,
    )

    state = models.JSONField(default=dict, blank=True, encoder=PostgresJSONEncoder)

    error_msg = models.TextField(
        default="",
        blank=True,
        help_text="The error message. If this is not set, the run is deemed successful.",
    )
    run_time = models.DurationField(default=datetime.timedelta, blank=True)
    run_status = models.TextField(default="", blank=True)

    error_code = models.IntegerField(
        null=True,
        default=None,
        blank=True,
        help_text="The HTTP status code of the error. If this is not set, 500 is assumed.",
    )
    error_type = models.TextField(
        default="", blank=True, help_text="The exception type"
    )

    hidden = models.BooleanField(default=False)
    is_flagged = models.BooleanField(default=False)

    price = models.IntegerField(default=0)
    transaction = models.ForeignKey(
        "app_users.AppUserTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="saved_runs",
    )

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    example_id = models.CharField(
        max_length=128, default=None, null=True, blank=True, help_text="(Deprecated)"
    )
    page_title = models.TextField(default="", blank=True, help_text="(Deprecated)")
    page_notes = models.TextField(default="", blank=True, help_text="(Deprecated)")

    retention_policy = models.IntegerField(
        choices=RetentionPolicy.choices, default=RetentionPolicy.keep
    )

    is_api_call = models.BooleanField(default=False)

    objects = SavedRunQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        unique_together = [
            ["workflow", "example_id"],
            ["run_id", "uid"],
        ]
        constraints = [
            models.CheckConstraint(
                # ensure that the parent is not the same as the current record
                check=~models.Q(parent=models.F("id")),
                name="parent_not_self",
            ),
        ]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["-updated_at"]),
            models.Index(fields=["workflow"]),
            models.Index(fields=["uid"]),
            models.Index(fields=["run_id", "uid"]),
            models.Index(fields=["workflow", "run_id", "uid"]),
            models.Index(fields=["workflow", "example_id", "run_id", "uid"]),
            models.Index(fields=["workflow", "example_id", "hidden"]),
            models.Index(fields=["workflow", "uid", "updated_at", "workspace"]),
        ]

    def __str__(self):
        from daras_ai_v2.breadcrumbs import get_title_breadcrumbs

        title = get_title_breadcrumbs(
            Workflow(self.workflow).page_cls, self, self.parent_published_run()
        ).h1_title
        return title or self.get_app_url()

    def parent_published_run(self) -> typing.Optional["PublishedRun"]:
        return self.parent_version and self.parent_version.published_run

    def get_app_url(self, query_params: dict = None):
        return Workflow(self.workflow).page_cls.app_url(
            example_id=self.example_id,
            run_id=self.run_id,
            uid=self.uid,
            query_params=query_params,
        )

    def to_dict(self) -> dict:
        from daras_ai_v2.base import StateKeys

        ret = self.state.copy()
        if self.updated_at:
            ret[StateKeys.updated_at] = self.updated_at
        if self.created_at:
            ret[StateKeys.created_at] = self.created_at
        if self.error_msg:
            ret[StateKeys.error_msg] = self.error_msg
        if self.run_time:
            ret[StateKeys.run_time] = self.run_time.total_seconds()
        if self.run_status:
            ret[StateKeys.run_status] = self.run_status
        if self.hidden:
            ret[StateKeys.hidden] = self.hidden
        if self.is_flagged:
            ret["is_flagged"] = self.is_flagged
        if self.price:
            ret["price"] = self.price
        return ret

    def set(self, state: dict):
        if not state:
            return

        self.copy_from_firebase_state(state)
        self.save()

    def copy_from_firebase_state(self, state: dict) -> "SavedRun":
        from daras_ai_v2.base import StateKeys

        state = state.copy()
        # ignore updated_at from firebase, we use auto_now=True
        state.pop(StateKeys.updated_at, None)
        # self.updated_at = _parse_dt() or EPOCH
        created_at = _parse_dt(state.pop(StateKeys.created_at, None))
        if created_at:
            self.created_at = created_at
        self.error_msg = state.pop(StateKeys.error_msg, None) or ""
        self.run_time = datetime.timedelta(
            seconds=state.pop(StateKeys.run_time, None) or 0
        )
        self.run_status = state.pop(StateKeys.run_status, None) or ""
        self.is_flagged = state.pop("is_flagged", False)
        self.state = state

        return self

    def submit_api_call(
        self,
        *,
        workspace: "Workspace",
        request_body: dict,
        enable_rate_limits: bool = False,
        deduct_credits: bool = True,
        parent_pr: typing.Optional["PublishedRun"] = None,
        current_user: AppUser | None = None,
    ) -> tuple["celery.result.AsyncResult", "SavedRun"]:
        from routers.api import submit_api_call

        # run in a thread to avoid messing up threadlocals
        with ThreadPool(1) as pool:
            page_cls = Workflow(self.workflow).page_cls
            if parent_pr and parent_pr.saved_run == self:
                # avoid passing run_id and uid for examples
                query_params = dict(example_id=parent_pr.published_run_id)
            else:
                query_params = page_cls.clean_query_params(
                    example_id=self.example_id, run_id=self.run_id, uid=self.uid
                )
            return pool.apply(
                submit_api_call,
                kwds=dict(
                    page_cls=page_cls,
                    query_params=query_params,
                    workspace=workspace,
                    current_user=current_user,
                    request_body=request_body,
                    enable_rate_limits=enable_rate_limits,
                    deduct_credits=deduct_credits,
                ),
            )

    def wait_for_celery_result(self, result: "celery.result.AsyncResult"):
        get_celery_result_db_safe(result)
        self.refresh_from_db()

    def get_creator(self) -> AppUser | None:
        if self.uid:
            return AppUser.objects.filter(uid=self.uid).first()
        else:
            return None

    @admin.display(description="Open in Gooey")
    def open_in_gooey(self):
        return open_in_new_tab(self.get_app_url(), label=self.get_app_url())

    def api_output(self, state: dict = None) -> dict:
        state = state or self.state
        if self.state.get("functions"):
            state["called_functions"] = [
                CalledFunctionResponse.from_db(called_fn)
                for called_fn in self.called_functions.all()
            ]
        return state


def _parse_dt(dt) -> datetime.datetime | None:
    if isinstance(dt, str):
        return datetime.datetime.fromisoformat(dt)
    elif isinstance(dt, datetime.datetime):
        return datetime.datetime.fromtimestamp(dt.timestamp(), dt.tzinfo)
    return None


class BotIntegrationQuerySet(models.QuerySet):
    @transaction.atomic()
    def add_fb_pages_for_user(
        self, created_by: AppUser, workspace: "Workspace", fb_pages: list[dict]
    ) -> list["BotIntegration"]:
        saved = []
        for fb_page in fb_pages:
            fb_page_id = fb_page["id"]
            ig_account_id = (
                fb_page.get("instagram_business_account", {}).get("id") or ""
            )
            # save to db / update exiting
            try:
                bi = BotIntegration.objects.get(
                    Q(fb_page_id=fb_page_id) | Q(ig_account_id=ig_account_id)
                )
            except BotIntegration.DoesNotExist:
                bi = BotIntegration(fb_page_id=fb_page_id)
            bi.created_by = created_by
            bi.workspace = workspace
            bi.fb_page_name = fb_page["name"]
            # bi.fb_user_access_token = user_access_token
            bi.fb_page_access_token = fb_page["access_token"]
            if ig_account_id:
                bi.ig_account_id = ig_account_id
            bi.ig_username = (
                fb_page.get("instagram_business_account", {}).get("username") or ""
            )
            if bi.ig_username:
                bi.name = bi.ig_username + " & " + bi.fb_page_name
                bi.platform = Platform.INSTAGRAM
            else:
                bi.platform = Platform.FACEBOOK
                bi.name = bi.fb_page_name
            bi.save()
            saved.append(bi)
        return saved


def validate_phonenumber(value):
    from phonenumber_field.phonenumber import to_python

    phone_number = to_python(value)
    if _is_invalid_phone_number(phone_number):
        raise ValidationError(
            "The phone number entered is not valid.", code="invalid_phone_number"
        )


class WhatsappPhoneNumberFormField(phonenumber_field.formfields.PhoneNumberField):
    default_validators = [validate_phonenumber]

    def to_python(self, value):
        from phonenumber_field.phonenumber import to_python

        phone_number = to_python(value, region=self.region)

        if phone_number in validators.EMPTY_VALUES:
            return self.empty_value

        if _is_invalid_phone_number(phone_number):
            raise ValidationError(self.error_messages["invalid"])

        return phone_number


def _is_invalid_phone_number(phone_number) -> bool:
    from phonenumber_field.phonenumber import PhoneNumber

    return (
        isinstance(phone_number, PhoneNumber)
        and not phone_number.is_valid()
        # facebook test numbers
        and not str(phone_number.as_e164).startswith("+1555")
    )


class WhatsappPhoneNumberField(phonenumber_field.modelfields.PhoneNumberField):
    default_validators = [validate_phonenumber]

    def formfield(self, **kwargs):
        kwargs["form_class"] = WhatsappPhoneNumberFormField
        return super().formfield(**kwargs)


class BotIntegration(models.Model):
    name = models.CharField(
        max_length=1024,
        help_text="The name of the bot (for display purposes)",
    )

    by_line = models.TextField(blank=True, default="")
    descripton = models.TextField(blank=True, default="")
    conversation_starters = models.JSONField(default=list, blank=True)
    photo_url = CustomURLField(default="", blank=True)
    website_url = CustomURLField(blank=True, default="")

    saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.SET_NULL,
        related_name="botintegrations",
        null=True,
        default=None,
        blank=True,
        help_text="The saved run that the bot is based on",
    )
    published_run = models.ForeignKey(
        "bots.PublishedRun",
        on_delete=models.SET_NULL,
        related_name="botintegrations",
        null=True,
        default=None,
        blank=True,
        help_text="The saved run that the bot is based on",
    )
    billing_account_uid = models.TextField(
        help_text="(Deprecated)", db_index=True, blank=True, default=""
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        related_name="botintegrations",
        null=True,
    )
    created_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,
        related_name="botintegrations",
        null=True,
    )
    user_language = models.TextField(
        default="",
        help_text="The response language (same as user language in video bots)",
        blank=True,
    )
    show_feedback_buttons = models.BooleanField(
        default=False,
        help_text="Show 👍/👎 buttons with every response",
    )
    platform = models.IntegerField(
        choices=Platform.choices,
        help_text="The platform that the bot is integrated with",
    )
    fb_page_id = models.CharField(
        max_length=256,
        blank=True,
        default=None,
        null=True,
        unique=True,
        help_text="Bot's Facebook page id (mandatory)",
    )
    fb_page_name = models.TextField(
        default="",
        blank=True,
        help_text="Bot's Facebook page name (only for display)",
    )
    fb_page_access_token = models.TextField(
        blank=True,
        default="",
        help_text="Bot's Facebook page access token (mandatory)",
        editable=False,
    )
    ig_account_id = models.CharField(
        max_length=256,
        blank=True,
        default=None,
        null=True,
        unique=True,
        help_text="Bot's Instagram account id (mandatory)",
    )
    ig_username = models.TextField(
        blank=True,
        default="",
        help_text="Bot's Instagram username (only for display)",
    )

    wa_phone_number = WhatsappPhoneNumberField(
        blank=True,
        default="",
        help_text="Bot's WhatsApp phone number (only for display)",
        validators=[validate_phonenumber],
    )
    wa_phone_number_id = models.CharField(
        max_length=256,
        blank=True,
        default=None,
        null=True,
        unique=True,
        help_text="Bot's WhatsApp phone number id (mandatory)",
    )

    wa_business_access_token = models.TextField(
        blank=True,
        default="",
        help_text="Bot's WhatsApp Business access token (mandatory if custom number) -- has these scopes: ['whatsapp_business_management', 'whatsapp_business_messaging', 'public_profile']",
    )
    wa_business_waba_id = models.TextField(
        blank=True,
        default="",
        help_text="Bot's WhatsApp Business API WABA id (only for display) -- this is the one seen on https://business.facebook.com/settings/whatsapp-business-accounts/",
    )
    wa_business_user_id = models.TextField(
        blank=True,
        default="",
        help_text="Bot's WhatsApp Business API user id (only for display)",
    )
    wa_business_name = models.TextField(
        blank=True,
        default="",
        help_text="Bot's WhatsApp Business API name (only for display)",
    )
    wa_business_account_name = models.TextField(
        blank=True,
        default="",
        help_text="Bot's WhatsApp Business API account name (only for display)",
    )
    wa_business_message_template_namespace = models.TextField(
        blank=True,
        default="",
        help_text="Bot's WhatsApp Business API message template namespace",
    )

    slack_team_id = models.CharField(
        max_length=256,
        blank=True,
        default=None,
        null=True,
        help_text="Bot's Slack team id (mandatory)",
    )
    slack_team_name = models.TextField(
        blank=True,
        default="",
        help_text="Bot's Slack team/workspace name (only for display)",
    )
    slack_channel_id = models.CharField(
        max_length=256,
        blank=True,
        default=None,
        null=True,
        help_text="Bot's Public Slack channel id (mandatory)",
    )
    slack_channel_name = models.TextField(
        blank=True,
        default="",
        help_text="Bot's Public Slack channel name without # (only for display)",
    )
    slack_channel_hook_url = models.TextField(
        blank=True,
        default="",
        help_text="Bot's Slack channel hook url (mandatory)",
    )
    slack_access_token = models.TextField(
        blank=True,
        default="",
        help_text="Bot's Slack access token (mandatory)",
        editable=False,
    )
    slack_read_receipt_msg = models.TextField(
        blank=True,
        default="Results may take up to 1 minute, we appreciate your patience.",
        help_text="Bot's Slack read receipt message - if set, and platform is Slack, the bot will send this message to mark the user message as read and then delete it when it has a response ready",
    )
    slack_create_personal_channels = models.BooleanField(
        default=True,
        help_text="If set, the bot will create a personal channel for each user in the public channel",
    )

    web_allowed_origins = models.JSONField(
        default=list,
        blank=True,
        help_text="List of allowed domains for the bot's web integration",
    )
    web_config_extras = models.JSONField(
        default=dict,
        blank=True,
        help_text="Extra configuration for the bot's web integration",
    )

    twilio_phone_number = phonenumber_field.modelfields.PhoneNumberField(
        blank=True,
        null=True,
        default=None,
        unique=True,
        help_text="Twilio phone number as found on twilio.com/console/phone-numbers/incoming (mandatory)",
    )
    twilio_phone_number_sid = models.TextField(
        blank=True,
        default="",
        help_text="Twilio phone number sid as found on twilio.com/console/phone-numbers/incoming",
    )
    twilio_account_sid = models.TextField(
        blank=True,
        default="",
        help_text="Account SID, required if using api_key to authenticate",
    )
    twilio_username = models.TextField(
        blank=True,
        default="",
        help_text="Username to authenticate with, either account_sid or api_key",
    )
    twilio_password = models.TextField(
        blank=True,
        default="",
        help_text="Password to authenticate with, auth_token (if using account_sid) or api_secret (if using api_key)",
    )
    twilio_use_missed_call = models.BooleanField(
        default=False,
        help_text="If true, the bot will reject incoming calls and call back the user instead so they don't get charged for the call",
    )
    twilio_initial_text = models.TextField(
        default="",
        blank=True,
        help_text="The initial text to send to the user when a call is started",
    )
    twilio_initial_audio_url = models.TextField(
        default="",
        blank=True,
        help_text="The initial audio url to play to the user when a call is started",
    )
    twilio_waiting_text = models.TextField(
        default="",
        blank=True,
        help_text="The text to send to the user while waiting for a response if using sms",
    )
    twilio_waiting_audio_url = models.TextField(
        default="",
        blank=True,
        help_text="The audio url to play to the user while waiting for a response if using voice",
    )
    twilio_fresh_conversation_per_call = models.BooleanField(
        default=False,
        help_text="If set, the bot will start a new conversation for each call",
    )

    streaming_enabled = models.BooleanField(
        default=True,
        help_text="If set, the bot will stream messages to the frontend",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BotIntegrationQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        unique_together = [
            ("slack_channel_id", "slack_team_id"),
            ("twilio_phone_number", "twilio_account_sid"),
        ]
        indexes = [
            models.Index(fields=["workspace", "platform"]),
            models.Index(fields=["fb_page_id", "ig_account_id"]),
        ]

    def __str__(self):
        platform_name = self.get_display_name()
        if self.name and platform_name and self.name != platform_name:
            return f"{self.name} ({platform_name})"
        else:
            return self.name or platform_name

    def get_active_saved_run(self) -> SavedRun | None:
        if self.published_run:
            return self.published_run.saved_run
        elif self.saved_run:
            return self.saved_run
        else:
            return None

    def get_display_name(self):
        return (
            (self.wa_phone_number and self.wa_phone_number.as_international)
            or self.wa_phone_number_id
            or self.fb_page_name
            or self.fb_page_id
            or self.ig_username
            or " | #".join(
                filter(None, [self.slack_team_name, self.slack_channel_name])
            )
            or (self.twilio_phone_number and self.twilio_phone_number.as_international)
            or self.name
            or (
                self.platform == Platform.WEB
                and f"Integration ID {self.api_integration_id()}"
            )
        )

    get_display_name.short_description = "Bot"

    def api_integration_id(self) -> str:
        from routers.bots_api import api_hashids

        return api_hashids.encode(self.id)

    def get_web_widget_config(self, target="#gooey-embed") -> dict:
        config = self.web_config_extras | dict(
            target=target,
            integration_id=self.api_integration_id(),
            branding=(
                self.web_config_extras.get("branding", {})
                | dict(
                    name=self.name,
                    byLine=self.by_line,
                    description=self.descripton,
                    conversationStarters=self.conversation_starters,
                    photoUrl=self.photo_url,
                    websiteUrl=self.website_url,
                )
            ),
        )
        if settings.DEBUG:
            from routers.bots_api import stream_create

            config["apiUrl"] = get_api_route_url(stream_create)
        return config

    def translate(self, text: str) -> str:
        from daras_ai_v2.asr import run_google_translate, should_translate_lang

        if text and should_translate_lang(self.user_language):
            active_run = self.get_active_saved_run()
            return run_google_translate(
                [text],
                self.user_language,
                glossary_url=(
                    active_run.state.get("output_glossary") if active_run else None
                ),
            )[0]
        else:
            return text

    def get_twilio_client(self):
        import twilio.rest

        return twilio.rest.Client(
            account_sid=self.twilio_account_sid or settings.TWILIO_ACCOUNT_SID,
            username=self.twilio_username or settings.TWILIO_API_KEY_SID,
            password=self.twilio_password or settings.TWILIO_API_KEY_SECRET,
        )


class BotIntegrationAnalysisRun(models.Model):
    bot_integration = models.ForeignKey(
        "BotIntegration",
        on_delete=models.CASCADE,
        related_name="analysis_runs",
    )
    saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.CASCADE,
        related_name="analysis_runs",
        null=True,
        blank=True,
        default=None,
    )
    published_run = models.ForeignKey(
        "bots.PublishedRun",
        on_delete=models.CASCADE,
        related_name="analysis_runs",
        null=True,
        blank=True,
        default=None,
    )

    cooldown_period = models.DurationField(
        help_text="The time period to wait before running the analysis again",
        null=True,
        blank=True,
        default=None,
    )

    last_run_at = models.DateTimeField(
        null=True, blank=True, default=None, editable=False
    )
    scheduled_task_id = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(editable=False, blank=True, default=timezone.now)

    class Meta:
        unique_together = [
            ("bot_integration", "saved_run", "published_run"),
        ]
        constraints = [
            # ensure only one of saved_run or published_run is set
            models.CheckConstraint(
                check=models.Q(saved_run__isnull=False)
                ^ models.Q(published_run__isnull=False),
                name="saved_run_xor_published_run",
            ),
        ]

    def get_active_saved_run(self) -> SavedRun:
        if self.published_run:
            return self.published_run.saved_run
        elif self.saved_run:
            return self.saved_run
        else:
            raise ValueError("No saved run found")


class BotIntegrationScheduledRun(models.Model):
    bot_integration = models.ForeignKey(
        "BotIntegration",
        on_delete=models.CASCADE,
        related_name="scheduled_runs",
    )
    saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.CASCADE,
        related_name="scheduled_runs",
        null=True,
        blank=True,
        default=None,
    )
    published_run = models.ForeignKey(
        "bots.PublishedRun",
        on_delete=models.CASCADE,
        related_name="scheduled_runs",
        null=True,
        blank=True,
        default=None,
    )

    last_run_at = models.DateTimeField(null=True, blank=True, default=None)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # ensure only one of saved_run or published_run is set
            models.CheckConstraint(
                check=models.Q(saved_run__isnull=False)
                ^ models.Q(published_run__isnull=False),
                name="bi_scheduled_runs_saved_run_xor_published_run",
            )
        ]

    def clean(self):
        if (self.published_run or self.saved_run).workflow != Workflow.FUNCTIONS:
            raise ValidationError("Expected a Functions workflow")
        return super().clean()

    def get_app_url(self) -> str:
        if self.published_run:
            return self.published_run.get_app_url()
        elif self.saved_run:
            return self.saved_run.get_app_url()
        else:
            raise ValueError("No saved run found")

    def get_runs(self) -> tuple[SavedRun, PublishedRun | None]:
        if self.published_run:
            return self.published_run.saved_run, self.published_run
        elif self.saved_run:
            return self.saved_run, None
        else:
            raise ValueError("No saved run found")


class ConvoState(models.IntegerChoices):
    INITIAL = 0, "Initial"
    ASK_FOR_FEEDBACK_THUMBS_UP = 1, "Ask for feedback (👍)"
    ASK_FOR_FEEDBACK_THUMBS_DOWN = 2, "Ask for feedback (👎)"


class ConversationQuerySet(models.QuerySet):
    def distinct_by_user_id(self) -> QuerySet["Conversation"]:
        """Get unique conversations"""
        return self.distinct(*Conversation.user_id_fields)

    def to_df(self, tz=pytz.timezone(settings.TIME_ZONE)) -> "pd.DataFrame":
        import pandas as pd

        qs = self.all()
        rows = []
        for convo in qs[:1000]:
            convo: Conversation
            row = {
                "USER": convo.get_display_name(),
                "BOT INTEGRATION": str(convo.bot_integration),
                "CREATED AT": convo.created_at.astimezone(tz).replace(tzinfo=None),
                "MESSAGES": convo.messages.count(),
            }
            try:
                row |= {
                    "LAST MESSAGE": convo.messages.latest()
                    .created_at.astimezone(tz)
                    .replace(tzinfo=None),
                    "DELTA HOURS": round(
                        convo.last_active_delta().total_seconds() / 3600
                    ),
                    "D1": convo.d1(),
                    "D7": convo.d7(),
                    "D30": convo.d30(),
                }
            except Message.DoesNotExist:
                pass
            rows.append(row)
        df = pd.DataFrame.from_records(rows)
        return df

    def to_df_format(
        self, tz=pytz.timezone(settings.TIME_ZONE), row_limit=1000
    ) -> "pd.DataFrame":
        import pandas as pd

        qs = self.all()
        rows = []
        for convo in qs[:row_limit]:
            convo: Conversation
            row = {
                "Name": convo.get_display_name(),
                "Messages": convo.messages.count(),
                "Correct Answers": convo.messages.filter(
                    analysis_result__contains={"Answered": True}
                ).count(),
                "Thumbs up": convo.messages.filter(
                    feedbacks__rating=Feedback.Rating.RATING_THUMBS_UP
                ).count(),
                "Thumbs down": convo.messages.filter(
                    feedbacks__rating=Feedback.Rating.RATING_THUMBS_DOWN
                ).count(),
            }
            try:
                first_time = (
                    convo.messages.earliest()
                    .created_at.astimezone(tz)
                    .replace(tzinfo=None)
                )
                last_time = (
                    convo.messages.latest()
                    .created_at.astimezone(tz)
                    .replace(tzinfo=None)
                )
                row |= {
                    "Last Sent": last_time.strftime(settings.SHORT_DATETIME_FORMAT),
                    "First Sent": first_time.strftime(settings.SHORT_DATETIME_FORMAT),
                    "A7": last_time
                    > datetime.datetime.now() - datetime.timedelta(days=7),
                    "A30": last_time
                    > datetime.datetime.now() - datetime.timedelta(days=30),
                    "R1": last_time - first_time < datetime.timedelta(days=1),
                    "R7": last_time - first_time < datetime.timedelta(days=7),
                    "R30": last_time - first_time < datetime.timedelta(days=30),
                    "Delta Hours": round(
                        convo.last_active_delta().total_seconds() / 3600
                    ),
                }
            except Message.DoesNotExist:
                pass
            row |= {
                "Created At": convo.created_at.astimezone(tz).replace(tzinfo=None),
                "Bot": str(convo.bot_integration),
            }
            rows.append(row)
        df = pd.DataFrame.from_records(
            rows,
            columns=[
                "Name",
                "Messages",
                "Correct Answers",
                "Thumbs up",
                "Thumbs down",
                "Last Sent",
                "First Sent",
                "A7",
                "A30",
                "R1",
                "R7",
                "R30",
                "Delta Hours",
                "Created At",
                "Bot",
            ],
        )
        return df


class Conversation(models.Model):
    bot_integration = models.ForeignKey(
        "BotIntegration", on_delete=models.CASCADE, related_name="conversations"
    )

    state = models.IntegerField(
        choices=ConvoState.choices,
        default=ConvoState.INITIAL,
    )

    fb_page_id = models.TextField(
        blank=True,
        default="",
        db_index=True,
        help_text="User's Facebook page id (mandatory)",
    )
    fb_page_name = models.TextField(
        default="",
        blank=True,
        help_text="User's Facebook page name (only for display)",
    )
    fb_page_access_token = models.TextField(
        blank=True,
        default="",
        help_text="User's Facebook page access token (mandatory)",
        editable=False,
    )
    ig_account_id = models.TextField(
        blank=True,
        default="",
        db_index=True,
        help_text="User's Instagram account id (required if platform is Instagram)",
    )
    ig_username = models.TextField(
        blank=True,
        default="",
        help_text="User's Instagram username (only for display)",
    )

    wa_phone_number = WhatsappPhoneNumberField(
        blank=True,
        default="",
        db_index=True,
        help_text="User's WhatsApp phone number (required if platform is WhatsApp)",
    )

    slack_user_id = models.TextField(
        max_length=256,
        blank=True,
        default=None,
        null=True,
        help_text="User's Slack ID (mandatory)",
    )
    slack_team_id = models.TextField(
        max_length=256,
        blank=True,
        default=None,
        null=True,
        help_text="Slack team id - redundant with bot integration (mandatory)",
    )
    slack_user_name = models.TextField(
        blank=True,
        default="",
        help_text="User's name in slack (only for display)",
    )
    slack_channel_id = models.TextField(
        max_length=256,
        blank=True,
        default=None,
        null=True,
        help_text="Slack channel id, can be different than the bot integration's public channel (mandatory)",
    )
    slack_channel_name = models.TextField(
        blank=True,
        default="",
        help_text="Bot's Slack channel name without # (only for display)",
    )
    slack_channel_is_personal = models.BooleanField(
        default=False,
        help_text="Whether this is a personal slack channel between the bot and the user",
    )

    twilio_phone_number = phonenumber_field.modelfields.PhoneNumberField(
        blank=True,
        default="",
        help_text="User's Twilio phone number (mandatory)",
    )
    twilio_call_sid = models.TextField(
        blank=True,
        default="",
        help_text="Twilio call sid (only used if each call is a new conversation)",
    )

    web_user_id = models.CharField(
        max_length=512,
        blank=True,
        default=None,
        null=True,
        help_text="User's web user id (mandatory if platform is WEB)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    reset_at = models.DateTimeField(null=True, blank=True, default=None)

    objects = ConversationQuerySet.as_manager()

    user_id_fields = [
        "fb_page_id",
        "ig_account_id",
        "slack_user_id",
        "web_user_id",
        "wa_phone_number",
        "twilio_phone_number",
    ]

    class Meta:
        unique_together = [
            ("slack_channel_id", "slack_user_id", "slack_team_id"),
        ]
        indexes = [
            models.Index(fields=["bot_integration", "fb_page_id", "ig_account_id"]),
            models.Index(fields=["bot_integration", "wa_phone_number"]),
            models.Index(
                fields=[
                    "bot_integration",
                    "slack_user_id",
                    "slack_team_id",
                    "slack_channel_is_personal",
                ],
            ),
            models.Index(
                fields=["bot_integration", "twilio_phone_number", "twilio_call_sid"]
            ),
            models.Index(fields=["-created_at", "bot_integration"]),
        ]

    def __str__(self):
        return f"{self.get_display_name()} <> {self.bot_integration}"

    def get_display_name(self):
        return (
            (self.wa_phone_number and self.wa_phone_number.as_international)
            or " | ".join(
                filter(
                    None,
                    [
                        (
                            self.twilio_phone_number
                            and self.twilio_phone_number.as_international
                        ),
                        self.twilio_call_sid,
                    ],
                )
            )
            or self.ig_username
            or self.fb_page_name
            or " in #".join(
                filter(None, [self.slack_user_name, self.slack_channel_name])
            )
            or self.unique_user_id()
        )

    def unique_user_id(self) -> str | None:
        for col in self.user_id_fields:
            if value := getattr(self, col, None):
                return value
        return self.api_integration_id()

    get_display_name.short_description = "User"

    def last_active_delta(self) -> datetime.timedelta:
        return abs(self.messages.latest().created_at - self.created_at)

    last_active_delta.short_description = "Duration"

    def d1(self):
        return self.last_active_delta() > datetime.timedelta(days=1)

    d1.short_description = "D1"
    d1.boolean = True

    def d7(self):
        return self.last_active_delta() > datetime.timedelta(days=7)

    d7.short_description = "D7"
    d7.boolean = True

    def d30(self):
        return self.last_active_delta() > datetime.timedelta(days=30)

    d30.short_description = "D30"
    d30.boolean = True

    def msgs_for_llm_context(self):
        return self.messages.all().as_llm_context(reset_at=self.reset_at)

    def api_integration_id(self) -> str:
        from routers.bots_api import api_hashids

        return api_hashids.encode(self.id)


class MessageQuerySet(models.QuerySet):
    def previous_by_created_at(self):
        return self.model.objects.filter(
            id__in=self.annotate(
                prev_id=Subquery(
                    self.model.objects.filter(
                        created_at__lt=OuterRef("created_at"),
                    ).values("id")[:1]
                )
            ).values("prev_id")
        )

    def distinct_by_user_id(self) -> QuerySet["Message"]:
        """Get unique users"""
        return self.distinct(*Message.convo_user_id_fields)

    def to_df(
        self, tz=pytz.timezone(settings.TIME_ZONE), row_limit=10000
    ) -> "pd.DataFrame":
        import pandas as pd

        rows = [
            {
                "Sent": (
                    row["sent"]
                    .replace(tzinfo=None)
                    .strftime(settings.SHORT_DATETIME_FORMAT)
                ),
                "Name": row.get("name"),
                "User Message (EN)": row.get("user_message"),
                "Assistant Message (EN)": row.get("assistant_message"),
                "User Message (Local)": row.get("user_message_local"),
                "Assistant Message (Local)": row.get("assistant_message_local"),
                "Analysis Result": row.get("analysis_result"),
                "Feedback": row.get("feedback"),
                "Run Time": row.get("run_time_sec"),
                "Run URL": row.get("run_url"),
                "Input Images": ", ".join(row.get("input_images") or []),
                "Input Audio": row.get("input_audio"),
                "User Message ID": row.get("user_message_id"),
                "Conversation ID": row.get("conversation_id"),
            }
            for row in self.to_json(tz=tz, row_limit=row_limit)
            if row.get("sent")
        ]
        df = pd.DataFrame.from_records(rows)
        return df

    def to_json(
        self, tz=pytz.timezone(settings.TIME_ZONE), row_limit=10000
    ) -> list[dict]:
        from routers.bots_api import MSG_ID_PREFIX

        conversations = defaultdict(list)

        qs = self.order_by("-created_at").prefetch_related(
            "feedbacks", "conversation", "saved_run"
        )
        for message in qs[:row_limit]:
            message: Message
            rows = conversations[message.conversation_id]

            # since we've sorted by -created_at, we'll get alternating assistant and user messages
            if message.role == CHATML_ROLE_ASSISSTANT:
                row = {
                    "assistant_message": message.content,
                    "assistant_message_local": message.display_content,
                    "analysis_result": message.analysis_result,
                }
                rows.append(row)
                if message.feedbacks.first():
                    row["feedback"] = message.feedbacks.first().get_display_text()
                saved_run = message.saved_run
                if saved_run:
                    row["run_time_sec"] = int(saved_run.run_time.total_seconds())
                    row["run_url"] = saved_run.get_app_url()
                    input_images = saved_run.state.get("input_images")
                    if input_images:
                        row["input_images"] = input_images
                    input_audio = saved_run.state.get("input_audio")
                    if input_audio:
                        row["input_audio"] = input_audio

            elif message.role == CHATML_ROLE_USER and rows:
                row = rows[-1]
                row.update(
                    {
                        "sent": message.created_at.astimezone(tz),
                        "name": message.conversation.get_display_name(),
                        "user_message": message.content,
                        "user_message_local": message.display_content,
                        "user_message_id": (
                            message.platform_msg_id
                            and message.platform_msg_id.removeprefix(MSG_ID_PREFIX)
                        ),
                        "conversation_id": message.conversation.api_integration_id(),
                    }
                )

        return [
            row
            for rows in conversations.values()
            # reversed so that user message is first and easier to read
            for row in reversed(rows)
            # drop rows that have only one of user/assistant message
            if "user_message" in row and "assistant_message" in row
        ]

    def as_llm_context(
        self, limit: int = 50, reset_at: datetime.datetime = None
    ) -> list["ConversationEntry"]:
        if reset_at:
            self = self.filter(created_at__gt=reset_at)
        msgs = self.order_by("-created_at").prefetch_related("attachments")[:limit]
        entries = [None] * len(msgs)
        for i, msg in enumerate(reversed(msgs)):
            entries[i] = format_chat_entry(
                role=msg.role,
                content_text=msg.content,
                input_images=msg.attachments.filter(
                    metadata__mime_type__startswith="image/"
                ).values_list("url", flat=True),
            )
        return entries


class Message(models.Model):
    conversation = models.ForeignKey(
        "Conversation", on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(
        choices=(
            # ("system", "System"),
            (CHATML_ROLE_USER, "User"),
            (CHATML_ROLE_ASSISSTANT, "Bot"),
        ),
        max_length=10,
    )
    content = models.TextField(help_text="The content that the AI sees")

    display_content = models.TextField(
        blank=True,
        help_text="The local language content that's actually displayed to the user",
    )

    saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.SET_NULL,
        related_name="messages",
        null=True,
        blank=True,
        default=None,
        help_text="The saved run that generated this message",
    )

    platform_msg_id = models.TextField(
        blank=True,
        null=True,
        default=None,
        help_text="The platform's delivered message id",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    analysis_result = models.JSONField(
        blank=True,
        default=dict,
        help_text="The result of the analysis of this message",
    )
    analysis_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.SET_NULL,
        related_name="analysis_messages",
        null=True,
        blank=True,
        default=None,
        help_text="The analysis run that generated the analysis of this message",
    )

    question_answered = models.TextField(
        blank=True,
        default="",
        help_text="Bot's ability to answer given question (DEPRECATED)",
    )
    question_subject = models.TextField(
        blank=True,
        default="",
        help_text="Subject of given question (DEPRECATED)",
    )

    response_time = models.DurationField(
        default=None,
        null=True,
        help_text="The time it took for the bot to respond to the corresponding user message",
    )

    _analysis_started = False

    objects = MessageQuerySet.as_manager()

    convo_user_id_fields = [
        f"conversation__{col}" for col in Conversation.user_id_fields
    ]

    class Meta:
        ordering = ("-created_at",)
        get_latest_by = "created_at"
        unique_together = [
            ("platform_msg_id", "conversation"),
        ]
        indexes = [
            models.Index(fields=["conversation", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return Truncator(self.content).words(30)

    def local_lang(self):
        return Truncator(self.display_content).words(30)


class MessageAttachment(models.Model):
    message = models.ForeignKey(
        "bots.Message",
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    url = CustomURLField()
    metadata = models.ForeignKey(
        "files.FileMetadata",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="message_attachments",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        if self.metadata_id:
            return f"{self.metadata.name} ({self.url})"
        return self.url


class FeedbackQuerySet(models.QuerySet):
    def to_df(self, tz=pytz.timezone(settings.TIME_ZONE)) -> "pd.DataFrame":
        import pandas as pd

        qs = self.all().prefetch_related("message", "message__conversation")
        rows = []
        for feedback in qs[:10000]:
            feedback: Feedback
            row = {
                "USER": feedback.message.conversation.get_display_name(),
                "BOT": str(feedback.message.conversation.bot_integration),
                "USER MESSAGE CREATED AT": feedback.message.get_previous_by_created_at()
                .created_at.astimezone(tz)
                .replace(tzinfo=None),
                "USER MESSAGE (ENGLISH)": feedback.message.get_previous_by_created_at().content,
                "USER MESSAGE (ORIGINAL)": feedback.message.get_previous_by_created_at().display_content,
                "BOT MESSAGE CREATED AT": feedback.message.created_at.astimezone(
                    tz
                ).replace(tzinfo=None),
                "BOT MESSAGE (ENGLISH)": feedback.message.content,
                "BOT MESSAGE (ORIGINAL)": feedback.message.display_content,
                "FEEDBACK RATING": feedback.rating,
                "FEEDBACK (ORIGINAL)": feedback.text,
                "FEEDBACK (ENGLISH)": feedback.text_english,
                "FEEDBACK CREATED AT": feedback.created_at.astimezone(tz).replace(
                    tzinfo=None
                ),
                "QUESTION_ANSWERED": feedback.message.question_answered,
            }
            rows.append(row)
        df = pd.DataFrame.from_records(rows)
        return df

    def to_df_format(
        self, tz=pytz.timezone(settings.TIME_ZONE), row_limit=10000
    ) -> "pd.DataFrame":
        import pandas as pd

        qs = self.all().prefetch_related("message", "message__conversation")
        rows = []
        for feedback in qs[:row_limit]:
            feedback: Feedback
            row = {
                "Name": feedback.message.conversation.get_display_name(),
                "Question (EN)": feedback.message.get_previous_by_created_at().content,
                "Answer (EN)": feedback.message.content,
                "Sent": feedback.message.get_previous_by_created_at()
                .created_at.astimezone(tz)
                .replace(tzinfo=None)
                .strftime(settings.SHORT_DATETIME_FORMAT),
                "Question (Local)": feedback.message.get_previous_by_created_at().display_content,
                "Answer (Local)": feedback.message.display_content,
                "Rating": Feedback.Rating(feedback.rating).label,
                "Feedback (EN)": feedback.text_english,
                "Feedback (Local)": feedback.text,
                "Run URL": feedback.message.saved_run.get_app_url(),
            }
            rows.append(row)
        df = pd.DataFrame.from_records(
            rows,
            columns=[
                "Name",
                "Question (EN)",
                "Answer (EN)",
                "Sent",
                "Question (Local)",
                "Answer (Local)",
                "Rating",
                "Feedback (EN)",
                "Feedback (Local)",
                "Run URL",
            ],
        )
        return df


class Feedback(models.Model):
    message = models.ForeignKey(
        "Message", on_delete=models.CASCADE, related_name="feedbacks"
    )

    class Rating(models.IntegerChoices):
        RATING_THUMBS_UP = 1, "👍🏾"
        RATING_THUMBS_DOWN = 2, "👎🏾"

    class FeedbackCategory(models.IntegerChoices):
        UNSPECIFIED = 1, "Unspecified"
        INCOMING = 2, "Incoming"
        TRANSLATION = 3, "Translation"
        RETRIEVAL = 4, "Retrieval"
        SUMMARIZATION = 5, "Summarization"
        TRANSLATION_OF_ANSWER = 6, "Translation of answer"

    class FeedbackCreator(models.IntegerChoices):
        UNSPECIFIED = 1, "Unspecified"
        USER = 2, "User"
        FARMER = 3, "Farmer"
        AGENT = 4, "Agent"
        ADMIN = 5, "Admin"
        GOOEY_TEAM_MEMBER = 6, "Gooey team member"

    class Status(models.IntegerChoices):
        UNTRIAGED = 1, "Untriaged"
        TEST = 2, "Test"
        NEEDS_INVESTIGATION = 3, "Needs investigation"
        RESOLVED = 4, "Resolved"

    rating = models.IntegerField(
        choices=Rating.choices,
    )
    text = models.TextField(
        blank=True, default="", verbose_name="Feedback Text (Original)"
    )
    text_english = models.TextField(
        blank=True, default="", verbose_name="Feedback Text (English)"
    )
    status = models.IntegerField(
        choices=Status.choices,
        default=Status.UNTRIAGED,
    )
    category = models.IntegerField(
        choices=FeedbackCategory.choices,
        default=FeedbackCategory.UNSPECIFIED,
    )
    creator = models.IntegerField(
        choices=FeedbackCreator.choices,
        default=FeedbackCreator.UNSPECIFIED,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = FeedbackQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["-created_at"]),
        ]
        ordering = ["-created_at"]
        get_latest_by = "created_at"

    def __str__(self):
        ret = self.get_display_text()
        if self.message.content:
            ret += f" to “{Truncator(self.message.content).words(30)}”"
        return ret

    def get_display_text(self):
        ret = self.get_rating_display()
        text = self.text_english or self.text
        if text:
            ret += f" - “{Truncator(text).words(30)}”"
        return ret


class FeedbackComment(models.Model):
    feedback = models.ForeignKey(
        Feedback, on_delete=models.CASCADE, related_name="comments"
    )
    author = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class PublishedRunQuerySet(models.QuerySet):
    def get_or_create_with_version(
        self,
        *,
        workflow: Workflow,
        published_run_id: str,
        saved_run: SavedRun,
        user: AppUser | None,
        workspace: typing.Optional["Workspace"],
        title: str,
        notes: str,
        public_access: WorkflowAccessLevel | None = None,
        photo_url: str = "",
    ):
        return get_or_create_lazy(
            PublishedRun,
            workflow=workflow,
            published_run_id=published_run_id,
            create=lambda **kwargs: self.create_with_version(
                **kwargs,
                saved_run=saved_run,
                user=user,
                workspace=workspace,
                title=title,
                notes=notes,
                public_access=public_access,
                photo_url=photo_url,
            ),
        )

    def create_with_version(
        self,
        *,
        workflow: Workflow,
        published_run_id: str,
        saved_run: SavedRun,
        user: AppUser | None,
        workspace: typing.Optional["Workspace"],
        title: str,
        notes: str,
        public_access: WorkflowAccessLevel | None = None,
        photo_url: str = "",
    ):
        workspace_id = (
            workspace
            and workspace.id
            or PublishedRun._meta.get_field("workspace").get_default()
        )
        if not public_access:
            if workspace and workspace.can_have_private_published_runs():
                public_access = WorkflowAccessLevel.VIEW_ONLY
            else:
                public_access = WorkflowAccessLevel.FIND_AND_VIEW

        with transaction.atomic():
            pr = self.create(
                workflow=workflow,
                published_run_id=published_run_id,
                created_by=user,
                last_edited_by=user,
                workspace_id=workspace_id,
                title=title,
                photo_url=photo_url,
            )
            pr.add_version(
                user=user,
                saved_run=saved_run,
                title=title,
                public_access=public_access,
                notes=notes,
                photo_url=photo_url,
            )
            return pr


def get_default_published_run_workspace():
    from workspaces.models import Workspace

    created_by, _ = AppUser.objects.filter(
        email__endswith="dara.network",
    )[:1].get_or_create(
        defaults=dict(
            email="support@dara.network", is_anonymous=False, balance=0, uid="<_blank>"
        ),
    )
    return Workspace.objects.get_or_create(
        domain_name="dara.network",
        defaults=dict(
            name="Gooey.AI (Dara.network Inc)",
            created_by=created_by,
            is_paying=True,
        ),
    )[0].id


class PublishedRun(models.Model):
    # published_run_id was earlier SavedRun.example_id
    published_run_id = models.CharField(
        max_length=128,
        blank=True,
    )

    saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.PROTECT,
        related_name="published_runs",
        null=True,
    )
    workflow = models.IntegerField(
        choices=Workflow.choices,
    )
    title = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    public_access = models.IntegerField(
        choices=WorkflowAccessLevel.choices,
        default=WorkflowAccessLevel.FIND_AND_VIEW,
    )
    workspace_access = models.IntegerField(
        choices=WorkflowAccessLevel.choices,
        default=WorkflowAccessLevel.EDIT,
    )
    is_approved_example = models.BooleanField(default=False)
    example_priority = models.IntegerField(
        default=1,
        help_text="Priority of the example in the example list",
    )

    run_count = models.IntegerField(default=0)

    created_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="published_runs",
        blank=True,
    )
    last_edited_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        default=get_default_published_run_workspace,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PublishedRunQuerySet.as_manager()
    photo_url = CustomURLField(default="", blank=True)

    class Meta:
        get_latest_by = "updated_at"

        ordering = ["-updated_at"]
        unique_together = [
            ["workflow", "published_run_id"],
        ]

        indexes = [
            models.Index(fields=["workflow", "created_by"]),
            models.Index(fields=["workflow", "published_run_id"]),
            models.Index(
                fields=[
                    "is_approved_example",
                    "public_access",
                    "workspace_access",
                    "published_run_id",
                    "updated_at",
                    "workflow",
                    "example_priority",
                ]
            ),
            models.Index(
                fields=[
                    "-updated_at",
                    "workspace",
                    "created_by",
                    "public_access",
                    "workspace_access",
                ]
            ),
        ]

    def __str__(self):
        return self.title or self.get_app_url()

    @admin.display(description="Open in Gooey")
    def open_in_gooey(self):
        return open_in_new_tab(self.get_app_url(), label=self.get_app_url())

    def duplicate(
        self,
        *,
        user: AppUser,
        workspace: "Workspace",
        title: str,
        notes: str,
        public_access: WorkflowAccessLevel | None = None,
    ) -> "PublishedRun":
        return PublishedRun.objects.create_with_version(
            workflow=Workflow(self.workflow),
            published_run_id=get_random_doc_id(),
            saved_run=self.saved_run,
            user=user,
            workspace=workspace,
            title=title,
            notes=notes,
            public_access=public_access,
        )

    def get_app_url(self, query_params: dict = None):
        return Workflow(self.workflow).page_cls.app_url(
            example_id=self.published_run_id, query_params=query_params
        )

    def add_version(
        self,
        *,
        user: AppUser | None,
        saved_run: SavedRun,
        public_access: WorkflowAccessLevel | None = None,
        workspace_access: WorkflowAccessLevel | None = None,
        title: str = "",
        notes: str = "",
        change_notes: str = "",
        photo_url: str = "",
    ):
        assert saved_run.workflow == self.workflow

        if public_access is None:
            public_access = self.public_access
        if workspace_access is None:
            workspace_access = self.workspace_access
        with transaction.atomic():
            version = PublishedRunVersion(
                published_run=self,
                version_id=get_random_doc_id(),
                saved_run=saved_run,
                changed_by=user,
                title=title,
                notes=notes,
                public_access=public_access,
                workspace_access=workspace_access,
                change_notes=change_notes,
                photo_url=photo_url,
            )
            version.save()
            self.update_fields_to_latest_version()

    def is_root(self):
        return not self.published_run_id

    def update_fields_to_latest_version(self):
        latest_version = self.versions.latest()
        self.saved_run = latest_version.saved_run
        self.last_edited_by = latest_version.changed_by
        self.title = latest_version.title
        self.notes = latest_version.notes
        self.public_access = latest_version.public_access
        self.workspace_access = latest_version.workspace_access
        self.photo_url = latest_version.photo_url

        self.save()

    def get_share_icon(self):
        if self.workspace.is_personal:
            return WorkflowAccessLevel(self.public_access).get_public_sharing_icon()
        else:
            return WorkflowAccessLevel(self.workspace_access).get_team_sharing_icon()

    def get_share_badge_html(self):
        if self.workspace.is_personal:
            perm = WorkflowAccessLevel(self.public_access)
            return f"{perm.get_public_sharing_icon()} {perm.get_public_sharing_label()}"
        else:
            perm = WorkflowAccessLevel(self.workspace_access)
            return f"{perm.get_team_sharing_icon()} {perm.get_team_sharing_label()}"

    def submit_api_call(
        self,
        *,
        workspace: "Workspace",
        request_body: dict,
        enable_rate_limits: bool = False,
        deduct_credits: bool = True,
        current_user: AppUser | None = None,
    ) -> tuple["celery.result.AsyncResult", "SavedRun"]:
        return self.saved_run.submit_api_call(
            workspace=workspace,
            current_user=current_user,
            request_body=request_body,
            enable_rate_limits=enable_rate_limits,
            deduct_credits=deduct_credits,
            parent_pr=self,
        )

    @classmethod
    def approved_example_q(cls):
        return (
            Q(is_approved_example=True)
            & ~Q(public_access=WorkflowAccessLevel.VIEW_ONLY.value)
            & ~Q(published_run_id="")
        )


class PublishedRunVersion(models.Model):
    version_id = models.CharField(max_length=128, unique=True)

    published_run = models.ForeignKey(
        PublishedRun,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    saved_run = models.ForeignKey(
        SavedRun,
        on_delete=models.PROTECT,
        related_name="published_run_versions",
    )
    changed_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    title = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    change_notes = models.TextField(blank=True, default="")
    public_access = models.IntegerField(
        choices=WorkflowAccessLevel.choices,
        default=WorkflowAccessLevel.VIEW_ONLY,
    )
    workspace_access = models.IntegerField(
        choices=WorkflowAccessLevel.choices,
        default=WorkflowAccessLevel.EDIT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    photo_url = CustomURLField(default="", blank=True)

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = "created_at"
        indexes = [
            models.Index(fields=["published_run", "-created_at"]),
            models.Index(fields=["version_id"]),
            models.Index(fields=["changed_by"]),
        ]

    def __str__(self):
        return f"{self.published_run} - {self.version_id}"
