import datetime
import typing
from multiprocessing.pool import ThreadPool

import pytz
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models import Q, IntegerChoices
from django.utils import timezone
from django.utils.text import Truncator
from phonenumber_field.modelfields import PhoneNumberField

from app_users.models import AppUser
from bots.admin_links import open_in_new_tab
from bots.custom_fields import PostgresJSONEncoder, CustomURLField
from daras_ai_v2.crypto import get_random_doc_id
from daras_ai_v2.language_model import format_chat_entry
from functions.models import CalledFunction, CalledFunctionResponse
from gooeysite.custom_create import get_or_create_lazy

if typing.TYPE_CHECKING:
    from daras_ai_v2.base import BasePage
    import celery.result

CHATML_ROLE_USER = "user"
CHATML_ROLE_ASSISSTANT = "assistant"

EPOCH = datetime.datetime.utcfromtimestamp(0)


class PublishedRunVisibility(models.IntegerChoices):
    UNLISTED = 1
    PUBLIC = 2

    def help_text(self):
        match self:
            case PublishedRunVisibility.UNLISTED:
                return "Only me + people with a link"
            case PublishedRunVisibility.PUBLIC:
                return "Public"
            case _:
                return self.label

    def get_badge_html(self):
        match self:
            case PublishedRunVisibility.UNLISTED:
                return '<i class="fa-regular fa-lock"></i> Private'
            case PublishedRunVisibility.PUBLIC:
                return '<i class="fa-regular fa-globe"></i> Public'
            case _:
                raise NotImplementedError(self)


class Platform(models.IntegerChoices):
    FACEBOOK = (1, "Facebook Messenger")
    INSTAGRAM = (2, "Instagram")
    WHATSAPP = (3, "WhatsApp")
    SLACK = (4, "Slack")
    WEB = (5, "Web")

    def get_icon(self):
        match self:
            case Platform.WEB:
                return f'<i class="fa-regular fa-globe"></i>'
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
                short_title=(
                    self.page_cls.get_root_published_run().title or self.page_cls.title
                ),
                default_image=self.page_cls.explore_image or "",
                meta_title=(
                    self.page_cls.get_root_published_run().title or self.page_cls.title
                ),
                meta_description=(
                    self.page_cls().preview_description(state={})
                    or self.page_cls.get_root_published_run().notes
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

    state = models.JSONField(default=dict, blank=True, encoder=PostgresJSONEncoder)

    error_msg = models.TextField(default="", blank=True)
    run_time = models.DurationField(default=datetime.timedelta, blank=True)
    run_status = models.TextField(default="", blank=True)

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
            models.Index(fields=["workflow", "uid", "updated_at"]),
        ]

    def __str__(self):
        from daras_ai_v2.breadcrumbs import get_title_breadcrumbs

        title = get_title_breadcrumbs(
            Workflow(self.workflow).page_cls, self, self.parent_published_run()
        ).h1_title
        return title or self.get_app_url()

    def parent_published_run(self) -> typing.Optional["PublishedRun"]:
        return self.parent_version and self.parent_version.published_run

    def get_app_url(self):
        return Workflow(self.workflow).page_cls.app_url(
            example_id=self.example_id, run_id=self.run_id, uid=self.uid
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
        current_user: AppUser,
        request_body: dict,
        enable_rate_limits: bool = False,
    ) -> tuple["celery.result.AsyncResult", "SavedRun"]:
        from routers.api import submit_api_call

        # run in a thread to avoid messing up threadlocals
        with ThreadPool(1) as pool:
            page, result, run_id, uid = pool.apply(
                submit_api_call,
                kwds=dict(
                    page_cls=Workflow(self.workflow).page_cls,
                    query_params=dict(
                        example_id=self.example_id, run_id=self.run_id, uid=self.uid
                    ),
                    user=current_user,
                    request_body=request_body,
                    enable_rate_limits=enable_rate_limits,
                ),
            )
        return result, page.run_doc_sr(run_id, uid)

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
    def reset_fb_pages_for_user(
        self, uid: str, fb_pages: list[dict]
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
            bi.billing_account_uid = uid
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
        # delete pages that are no longer connected for this user
        self.filter(
            Q(platform=Platform.FACEBOOK) | Q(platform=Platform.INSTAGRAM),
            billing_account_uid=uid,
        ).exclude(
            id__in=[bi.id for bi in saved],
        ).delete()
        return saved


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
        help_text="The gooey account uid where the credits will be deducted from",
        db_index=True,
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

    wa_phone_number = PhoneNumberField(
        blank=True,
        default="",
        help_text="Bot's WhatsApp phone number (only for display)",
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

    streaming_enabled = models.BooleanField(
        default=False,
        help_text="If set, the bot will stream messages to the frontend (Slack & Web only)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BotIntegrationQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        unique_together = [
            ("slack_channel_id", "slack_team_id"),
        ]
        indexes = [
            models.Index(fields=["billing_account_uid", "platform"]),
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
            or self.name
            or (
                self.platform == Platform.WEB
                and f"Integration ID {self.api_integration_id()}"
            )
        )

    get_display_name.short_description = "Bot"

    def api_integration_id(self):
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
        return config


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


class ConvoState(models.IntegerChoices):
    INITIAL = 0, "Initial"
    ASK_FOR_FEEDBACK_THUMBS_UP = 1, "Ask for feedback (👍)"
    ASK_FOR_FEEDBACK_THUMBS_DOWN = 2, "Ask for feedback (👎)"


class ConversationQuerySet(models.QuerySet):
    def get_unique_users(self) -> "ConversationQuerySet":
        """Get unique conversations"""
        return self.distinct(
            "fb_page_id", "ig_account_id", "wa_phone_number", "slack_user_id"
        )

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

    wa_phone_number = PhoneNumberField(
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
            models.Index(fields=["-created_at", "bot_integration"]),
        ]

    def __str__(self):
        return f"{self.get_display_name()} <> {self.bot_integration}"

    def get_display_name(self):
        return (
            (self.wa_phone_number and self.wa_phone_number.as_international)
            or self.ig_username
            or self.fb_page_name
            or " in #".join(
                filter(None, [self.slack_user_name, self.slack_channel_name])
            )
            or self.fb_page_id
            or self.slack_user_id
            or self.web_user_id
        )

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


class MessageQuerySet(models.QuerySet):
    def to_df(self, tz=pytz.timezone(settings.TIME_ZONE)) -> "pd.DataFrame":
        import pandas as pd

        qs = self.all().prefetch_related("feedbacks")
        rows = []
        for message in qs[:10000]:
            message: Message
            row = {
                "USER": message.conversation.get_display_name(),
                "BOT": str(message.conversation.bot_integration),
                "CREATED AT": message.created_at.astimezone(tz).replace(tzinfo=None),
                "MESSAGE (ENGLISH)": message.content,
                "MESSAGE (ORIGINAL)": message.display_content,
                "ROLE": message.get_role_display(),
                "QUESTION_ANSWERED": message.question_answered,
                "QUESTION_SUBJECT": message.question_subject,
            }
            row |= {
                f"FEEDBACK {i + 1}": feedback.get_display_text()
                for i, feedback in enumerate(message.feedbacks.all())
            }
            rows.append(row)
        df = pd.DataFrame.from_records(rows)
        return df

    def to_df_format(
        self, tz=pytz.timezone(settings.TIME_ZONE), row_limit=10000
    ) -> "pd.DataFrame":
        import pandas as pd

        qs = self.all().prefetch_related("feedbacks")
        rows = []
        for message in qs[:row_limit]:
            message: Message
            row = {
                "Name": message.conversation.get_display_name(),
                "Role": message.role,
                "Message (EN)": message.content,
                "Sent": message.created_at.astimezone(tz)
                .replace(tzinfo=None)
                .strftime(settings.SHORT_DATETIME_FORMAT),
                "Message (Local)": message.display_content,
                "Analysis JSON": message.analysis_result,
                "Feedback": (
                    message.feedbacks.first().get_display_text()
                    if message.feedbacks.first()
                    else None
                ),  # only show first feedback as per Sean's request
                "Run Time": (
                    message.saved_run.run_time if message.saved_run else 0
                ),  # user messages have no run/run_time
                "Run URL": (
                    message.saved_run.get_app_url()
                    if message.saved_run and message.role == CHATML_ROLE_ASSISSTANT
                    else ""
                ),
                "Photo Input": ", ".join(
                    message.attachments.filter(
                        metadata__mime_type__startswith="image/"
                    ).values_list("url", flat=True)
                ),
                "Audio Input": ", ".join(
                    message.attachments.filter(
                        metadata__mime_type__startswith="audio/"
                    ).values_list("url", flat=True)
                ),
            }
            rows.append(row)
        df = pd.DataFrame.from_records(
            rows,
            columns=[
                "Name",
                "Role",
                "Message (EN)",
                "Sent",
                "Message (Local)",
                "Analysis JSON",
                "Feedback",
                "Run Time",
                "Run URL",
                "Photo Input",
                "Audio Input",
            ],
        )
        return df

    def to_df_analysis_format(
        self, tz=pytz.timezone(settings.TIME_ZONE), row_limit=10000
    ) -> "pd.DataFrame":
        import pandas as pd

        qs = self.filter(role=CHATML_ROLE_ASSISSTANT).prefetch_related("feedbacks")
        rows = []
        for message in qs[:row_limit]:
            message: Message
            row = {
                "Name": message.conversation.get_display_name(),
                "Question (EN)": message.get_previous_by_created_at().content,
                "Answer (EN)": message.content,
                "Sent": message.created_at.astimezone(tz)
                .replace(tzinfo=None)
                .strftime(settings.SHORT_DATETIME_FORMAT),
                "Question (Local)": message.get_previous_by_created_at().display_content,
                "Answer (Local)": message.display_content,
                "Analysis JSON": message.analysis_result,
                "Run URL": (message.saved_run and message.saved_run.get_app_url()),
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
                "Analysis JSON",
                "Run URL",
            ],
        )
        return df

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
                content=msg.content,
                images=msg.attachments.filter(
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
        title: str,
        notes: str,
        visibility: PublishedRunVisibility,
    ):
        return get_or_create_lazy(
            PublishedRun,
            workflow=workflow,
            published_run_id=published_run_id,
            create=lambda **kwargs: self.create_with_version(
                **kwargs,
                saved_run=saved_run,
                user=user,
                title=title,
                notes=notes,
                visibility=visibility,
            ),
        )

    def create_with_version(
        self,
        *,
        workflow: Workflow,
        published_run_id: str,
        saved_run: SavedRun,
        user: AppUser | None,
        title: str,
        notes: str,
        visibility: PublishedRunVisibility,
    ):
        with transaction.atomic():
            pr = self.create(
                workflow=workflow,
                published_run_id=published_run_id,
                created_by=user,
                last_edited_by=user,
                title=title,
            )
            pr.add_version(
                user=user,
                saved_run=saved_run,
                title=title,
                visibility=visibility,
                notes=notes,
            )
            return pr


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
    visibility = models.IntegerField(
        choices=PublishedRunVisibility.choices,
        default=PublishedRunVisibility.UNLISTED,
    )
    is_approved_example = models.BooleanField(default=False)
    example_priority = models.IntegerField(
        default=1,
        help_text="Priority of the example in the example list",
    )

    created_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,  # TODO: set to sentinel instead (e.g. github's ghost user)
        null=True,
        related_name="published_runs",
    )
    last_edited_by = models.ForeignKey(
        "app_users.AppUser",
        on_delete=models.SET_NULL,  # TODO: set to sentinel instead (e.g. github's ghost user)
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PublishedRunQuerySet.as_manager()

    class Meta:
        get_latest_by = "updated_at"

        ordering = ["-updated_at"]
        unique_together = [
            ["workflow", "published_run_id"],
        ]

        indexes = [
            models.Index(fields=["workflow"]),
            models.Index(fields=["workflow", "created_by"]),
            models.Index(fields=["workflow", "published_run_id"]),
            models.Index(fields=["workflow", "visibility", "is_approved_example"]),
            models.Index(
                fields=[
                    "workflow",
                    "visibility",
                    "is_approved_example",
                    "published_run_id",
                ]
            ),
            models.Index(
                fields=[
                    "workflow",
                    "visibility",
                    "is_approved_example",
                    "published_run_id",
                    "example_priority",
                    "updated_at",
                ]
            ),
            models.Index(
                "created_by",
                "visibility",
                models.F("updated_at").desc(),
                name="published_run_cre_vis_upd_idx",
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
        title: str,
        notes: str,
        visibility: PublishedRunVisibility,
    ) -> "PublishedRun":
        return PublishedRun.objects.create_with_version(
            workflow=Workflow(self.workflow),
            published_run_id=get_random_doc_id(),
            saved_run=self.saved_run,
            user=user,
            title=title,
            notes=notes,
            visibility=visibility,
        )

    def get_app_url(self):
        return Workflow(self.workflow).page_cls.app_url(
            example_id=self.published_run_id
        )

    def add_version(
        self,
        *,
        user: AppUser | None,
        saved_run: SavedRun,
        visibility: PublishedRunVisibility,
        title: str,
        notes: str,
    ):
        assert saved_run.workflow == self.workflow

        with transaction.atomic():
            version = PublishedRunVersion(
                published_run=self,
                version_id=get_random_doc_id(),
                saved_run=saved_run,
                changed_by=user,
                title=title,
                notes=notes,
                visibility=visibility,
            )
            version.save()
            self.update_fields_to_latest_version()

    def is_editor(self, user: AppUser):
        return self.created_by == user

    def is_root(self):
        return not self.published_run_id

    def update_fields_to_latest_version(self):
        latest_version = self.versions.latest()
        self.saved_run = latest_version.saved_run
        self.last_edited_by = latest_version.changed_by
        self.title = latest_version.title
        self.notes = latest_version.notes
        self.visibility = latest_version.visibility

        self.save()

    def get_run_count(self):
        annotated_versions = self.versions.annotate(
            children_runs_count=models.Count("children_runs")
        )
        return (
            annotated_versions.aggregate(run_count=models.Sum("children_runs_count"))[
                "run_count"
            ]
            or 0
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
        on_delete=models.SET_NULL,  # TODO: set to sentinel instead (e.g. github's ghost user)
        null=True,
    )
    title = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    visibility = models.IntegerField(
        choices=PublishedRunVisibility.choices,
        default=PublishedRunVisibility.UNLISTED,
    )
    created_at = models.DateTimeField(auto_now_add=True)

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
