from __future__ import annotations

import typing

import phonenumber_field.formfields
import phonenumber_field.modelfields
from django.conf import settings
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from furl import furl

from app_users.models import AppUser
from bots.custom_fields import CustomURLField
from bots.models.workflow import WorkflowAccessLevel
from daras_ai_v2 import icons
from daras_ai_v2.fastapi_tricks import get_api_route_url, get_app_route_url
from managed_secrets.models import ManagedSecret

if typing.TYPE_CHECKING:
    from .published_run import PublishedRun
    from .saved_run import SavedRun


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
            case Platform.WHATSAPP:
                return icons.whatsapp
            case Platform.FACEBOOK:
                return icons.fb_messenger
            case Platform.INSTAGRAM:
                return icons.instagram
            case Platform.SLACK:
                return icons.slack
            case Platform.TWILIO:
                return icons.phone
            case _:
                return f'<i class="fa-brands fa-{self.name.lower()}"></i>'

    def get_title(self):
        match self:
            case Platform.TWILIO:
                return "Voice/SMS"
            case Platform.FACEBOOK:
                return "Messenger"
            case _:
                return self.label

    def get_demo_button_color(self) -> str | None:
        match self:
            case Platform.WEB:
                return None
            case Platform.WHATSAPP:
                return "#21d562"
            case Platform.FACEBOOK:
                return "#0466fb"
            case Platform.SLACK:
                return "#471549"
            case Platform.INSTAGRAM:
                return "#c20286"
            case Platform.TWILIO:
                return "#f22f46"


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
    ask_detailed_feedback = models.BooleanField(
        default=False,
        help_text="Ask for detailed feedback when users give a thumbs down (requires feedback buttons to be enabled)",
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

    disable_rate_limits = models.BooleanField(default=False)

    public_visibility = models.IntegerField(
        choices=WorkflowAccessLevel.choices,
        default=WorkflowAccessLevel.VIEW_ONLY,
        help_text="Controls whether this bot integration is listed on gooey.ai/chat & whether the demo button is shown",
    )

    demo_qr_code_image = models.TextField(
        null=True, blank=True, help_text="QR code image for the demo button"
    )
    demo_qr_code_run = models.ForeignKey(
        "SavedRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    demo_notes = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BotIntegrationQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        unique_together = [
            ("slack_channel_id", "slack_team_id"),
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
        if self.platform == Platform.TWILIO:
            bot_extension_number = self.get_extension_number()
            if bot_extension_number:
                return f"{self.twilio_phone_number.as_international} ex {bot_extension_number}"
            else:
                return (
                    self.twilio_phone_number
                    and self.twilio_phone_number.as_international
                )

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

    def get_bot_test_link(self) -> str | None:
        from routers.root import chat_route

        if self.wa_phone_number:
            return (furl("https://wa.me/") / self.wa_phone_number.as_e164).tostr()
        elif self.slack_team_id and self.slack_channel_id:
            return (
                furl("https://app.slack.com/client")
                / self.slack_team_id
                / self.slack_channel_id
            ).tostr()
        elif self.ig_username:
            return (furl("http://instagram.com/") / self.ig_username).tostr()
        elif self.fb_page_name:
            return (furl("https://www.facebook.com/") / self.fb_page_id).tostr()
        elif self.platform == Platform.WEB:
            return get_app_route_url(
                chat_route,
                path_params=dict(
                    integration_id=self.api_integration_id(),
                    integration_name=slugify(self.name) or "untitled",
                ),
            )
        elif self.twilio_phone_number:
            bot_extension_number = self.get_extension_number()
            tel_url = furl("tel:") / self.twilio_phone_number.as_e164
            if bot_extension_number:
                return f"{tel_url.tostr()},{bot_extension_number}"
            return tel_url.tostr()
        else:
            return None

    def get_extension_number(self) -> str | None:
        from number_cycling.models import BotExtension

        try:
            return str(BotExtension.objects.get(bot_integration=self).extension_number)
        except BotExtension.DoesNotExist:
            return None

    def api_integration_id(self) -> str:
        from routers.bots_api import api_hashids

        return api_hashids.encode(self.id)

    def get_web_widget_config(
        self, hostname: str | None, target="#gooey-embed"
    ) -> dict:
        config = self.web_config_extras | dict(
            target=target,
            integration_id=self.api_integration_id(),
            branding=self.get_web_widget_branding(),
        )

        google_maps_api_key = None
        try:
            google_maps_secret = self.workspace.managed_secrets.get(
                name__iexact="GOOGLE_MAPS_API_KEY"
            )
            google_maps_secret.load_value()
            google_maps_api_key = google_maps_secret.value
        except (ManagedSecret.DoesNotExist, ManagedSecret.NotFoundError):
            if hostname in settings.GOOGLE_MAPS_API_KEY_HOSTNAMES:
                google_maps_api_key = settings.GOOGLE_MAPS_API_KEY
        if google_maps_api_key:
            config["secrets"] = config.get("secrets") or {}
            config["secrets"]["GOOGLE_MAPS_API_KEY"] = google_maps_api_key

        if settings.DEBUG:
            from routers.bots_api import stream_create

            config["apiUrl"] = get_api_route_url(stream_create)
        return config

    def get_web_widget_branding(self) -> dict:
        return self.web_config_extras.get("branding", {}) | dict(
            name=self.name,
            byLine=self.by_line,
            description=self.descripton,
            conversationStarters=self.conversation_starters,
            photoUrl=self.photo_url,
            websiteUrl=self.website_url,
        )

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


class GraphType(models.IntegerChoices):
    display_values = 1, "Display as Text"
    table_count = 2, "Table of Counts"
    bar_count = 3, "Bar Chart of Counts"
    pie_count = 4, "Pie Chart of Counts"
    radar_count = 5, "Radar Plot of Counts"


class DataSelection(models.IntegerChoices):
    all = 1, "All Data"
    last = 2, "Last Analysis"
    convo_last = 3, "Last Analysis per Conversation"


class BotIntegrationAnalysisChart(models.Model):
    """
    Stores user-configured analysis chart settings for a BotIntegration.
    """

    bot_integration = models.ForeignKey(
        "BotIntegration",
        on_delete=models.CASCADE,
        related_name="analysis_charts",
    )

    result_field = models.TextField(
        help_text="The analysis result JSON field to visualize"
    )
    graph_type = models.IntegerField(
        choices=GraphType.choices,
        help_text="Type of graph to display",
    )
    data_selection = models.IntegerField(
        choices=DataSelection.choices,
        help_text="Data selection mode",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.result_field} ({self.get_graph_type_display()})"


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
        from bots.models import Workflow

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
