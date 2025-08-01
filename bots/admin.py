import datetime
import json

import django.db.models
from django import forms
from django.conf import settings
from django.contrib import admin
from django.db.models import Count, F, Max, Sum
from django.template import loader
from django.utils import dateformat
from django.utils.safestring import mark_safe
from django.utils.timesince import timesince

from app_users.models import AppUser
from bots.admin_links import change_obj_url, list_related_html_url, open_in_new_tab
from bots.models import (
    BotIntegration,
    BotIntegrationAnalysisChart,
    BotIntegrationAnalysisRun,
    BotIntegrationScheduledRun,
    Conversation,
    Feedback,
    FeedbackComment,
    Message,
    MessageAttachment,
    Platform,
    PublishedRun,
    PublishedRunVersion,
    SavedRun,
    Workflow,
    WorkflowMetadata,
)
from bots.tasks import create_personal_channels_for_all_members
from daras_ai_v2.fastapi_tricks import get_app_route_url
from daras_ai_v2.language_model import CHATML_ROLE_ASSISTANT
from gooeysite.custom_actions import export_to_csv, export_to_excel
from gooeysite.custom_filters import (
    JSONBExtractPath,
    related_json_field_summary,
)
from gooeysite.custom_widgets import JSONEditorWidget
from recipes.VideoBots import VideoBotsPage
from routers.root import integrations_stats_route

fb_fields = [
    "fb_page_id",
    "fb_page_name",
    "fb_page_access_token",
]
ig_fields = [
    "ig_account_id",
    "ig_username",
]
wa_fields = [
    "wa_phone_number",
    "wa_phone_number_id",
    "wa_business_access_token",
    "wa_business_waba_id",
    "wa_business_user_id",
    "wa_business_name",
    "wa_business_account_name",
    "wa_business_message_template_namespace",
]
slack_fields = [
    "slack_team_id",
    "slack_team_name",
    "slack_channel_id",
    "slack_channel_name",
    "slack_channel_hook_url",
    "slack_access_token",
    "slack_read_receipt_msg",
    "slack_create_personal_channels",
]
web_fields = [
    "by_line",
    "descripton",
    "conversation_starters",
    "photo_url",
    "website_url",
    "web_config_extras",
    "web_allowed_origins",
]
twilio_fields = [
    "twilio_phone_number",
    "twilio_phone_number_sid",
    "twilio_account_sid",
    "twilio_username",
    "twilio_password",
    "twilio_use_missed_call",
    "twilio_fresh_conversation_per_call",
    "twilio_initial_text",
    "twilio_initial_audio_url",
    "twilio_waiting_text",
    "twilio_waiting_audio_url",
]


class BotIntegrationAdminForm(forms.ModelForm):
    class Meta:
        model = BotIntegration
        fields = "__all__"
        widgets = {
            "platform": forms.Select(
                attrs={
                    "--hideshow-fields": ",".join(
                        fb_fields
                        + ig_fields
                        + wa_fields
                        + slack_fields
                        + web_fields
                        + twilio_fields
                    ),
                    f"--show-on-{Platform.FACEBOOK}": ",".join(fb_fields),
                    f"--show-on-{Platform.INSTAGRAM}": ",".join(fb_fields + ig_fields),
                    f"--show-on-{Platform.WHATSAPP}": ",".join(wa_fields),
                    f"--show-on-{Platform.SLACK}": ",".join(slack_fields),
                    f"--show-on-{Platform.WEB}": ",".join(web_fields),
                    f"--show-on-{Platform.TWILIO}": ",".join(twilio_fields),
                },
            ),
        }

    class Media:
        js = [
            "https://cdn.jsdelivr.net/gh/scientifichackers/django-hideshow@0.0.1/hideshow.js",
        ]


def create_personal_channels(modeladmin, request, queryset):
    for bi in queryset:
        create_personal_channels_for_all_members.delay(bi.id)
    modeladmin.message_user(
        request,
        f"Started creating personal channels for {queryset.count()} bots in the background.",
    )


class BotIntegrationAnalysisRunInline(admin.TabularInline):
    model = BotIntegrationAnalysisRun
    autocomplete_fields = ["saved_run", "published_run"]
    readonly_fields = ["last_run_at"]
    extra = 0


class BotIntegrationScheduledFunctionInline(admin.TabularInline):
    model = BotIntegrationScheduledRun
    autocomplete_fields = ["saved_run", "published_run"]
    readonly_fields = ["created_at"]
    extra = 0


class BotIntegrationAnalysisChartInline(admin.TabularInline):
    model = BotIntegrationAnalysisChart
    extra = 0


@admin.register(BotIntegration)
class BotIntegrationAdmin(admin.ModelAdmin):
    search_fields = [
        "name",
        "workspace__name",
        "created_by__display_name",
        "user_language",
        "fb_page_id",
        "fb_page_name",
        "fb_page_access_token",
        "ig_account_id",
        "ig_username",
        "wa_phone_number",
        "wa_phone_number_id",
        "slack_team_id",
        "slack_team_name",
        "slack_channel_id",
        "slack_channel_name",
        "slack_channel_hook_url",
        "slack_access_token",
        "twilio_phone_number",
    ]
    list_display = [
        "name",
        "get_display_name",
        "workspace",
        "created_by",
        "platform",
        "wa_phone_number",
        "twilio_phone_number",
        "created_at",
        "updated_at",
        "saved_run",
        "published_run",
        "has_analysis_runs",
    ]
    list_filter = ["platform"]

    form = BotIntegrationAdminForm

    autocomplete_fields = [
        "saved_run",
        "published_run",
        "workspace",
        "created_by",
        "demo_qr_code_run",
    ]

    formfield_overrides = {
        django.db.models.JSONField: {"widget": JSONEditorWidget},
    }

    inlines = [
        BotIntegrationAnalysisRunInline,
        BotIntegrationScheduledFunctionInline,
        BotIntegrationAnalysisChartInline,
    ]

    readonly_fields = [
        "fb_page_access_token",
        "slack_access_token",
        "slack_channel_hook_url",
        "view_analysis_results",
        "view_conversations",
        "view_messsages",
        "created_at",
        "updated_at",
        "api_integration_stats_url",
    ]

    fieldsets = [
        (
            None,
            {
                "fields": [
                    "name",
                    "saved_run",
                    "published_run",
                    "workspace",
                    "created_by",
                    "user_language",
                    "api_integration_stats_url",
                    "billing_account_uid",
                ],
            },
        ),
        (
            "Platform",
            {
                "fields": [
                    "platform",
                    *fb_fields,
                    *ig_fields,
                    *wa_fields,
                    *slack_fields,
                    *web_fields,
                    *twilio_fields,
                ]
            },
        ),
        (
            "Visibility & Demo",
            {
                "fields": [
                    "public_visibility",
                    "demo_qr_code_image",
                    "demo_qr_code_run",
                    "demo_notes",
                ]
            },
        ),
        (
            "Stats",
            {
                "fields": [
                    "view_conversations",
                    "view_messsages",
                    "created_at",
                    "updated_at",
                ]
            },
        ),
        (
            "Settings",
            {
                "fields": [
                    "streaming_enabled",
                    "show_feedback_buttons",
                    "disable_rate_limits",
                    "view_analysis_results",
                ]
            },
        ),
    ]

    actions = [create_personal_channels]

    @admin.display(description="Messages")
    def view_messsages(self, bi: BotIntegration):
        return list_related_html_url(
            Message.objects.filter(conversation__bot_integration=bi),
            query_param="conversation__bot_integration__id__exact",
            instance_id=bi.id,
        )

    @admin.display(description="Conversations")
    def view_conversations(self, bi: BotIntegration):
        return list_related_html_url(bi.conversations)

    @admin.display(description="Has Analysis Runs", boolean=True)
    def has_analysis_runs(self, bi: BotIntegration):
        return bi.analysis_runs.exists()

    @admin.display(description="Analysis Results")
    def view_analysis_results(self, bi: BotIntegration):
        msgs = Message.objects.filter(
            conversation__bot_integration=bi,
        ).exclude(
            analysis_result={},
        )
        results = related_json_field_summary(
            Message.objects,
            "analysis_result",
            qs=msgs,
            query_param="conversation__bot_integration__id__exact",
            instance_id=bi.id,
            max_keys=100,
        )
        html = loader.render_to_string(
            "anaylsis_result.html", context=dict(results=results)
        )
        html = mark_safe(html)
        return html

    @admin.display(description="Integration Stats")
    def api_integration_stats_url(self, bi: BotIntegration):
        if not bi.id:
            raise bi.DoesNotExist

        integration_id = bi.api_integration_id()
        return open_in_new_tab(
            url=get_app_route_url(
                integrations_stats_route,
                path_params=dict(
                    page_slug=VideoBotsPage.slug_versions[-1],
                    integration_id=integration_id,
                ),
            ),
            label=integration_id,
        )


@admin.register(PublishedRunVersion)
class PublishedRunVersionAdmin(admin.ModelAdmin):
    search_fields = ["id", "version_id", "published_run__published_run_id"]
    autocomplete_fields = ["published_run", "saved_run", "changed_by"]
    readonly_fields = ["created_at"]


class PublishedRunVersionInline(admin.TabularInline):
    model = PublishedRunVersion
    extra = 0
    autocomplete_fields = PublishedRunVersionAdmin.autocomplete_fields
    readonly_fields = PublishedRunVersionAdmin.readonly_fields


@admin.register(PublishedRun)
class PublishedRunAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "public_access",
        "view_user",
        "open_in_gooey",
        "linked_saved_run",
        "view_runs",
        "run_count",
        "created_at",
        "updated_at",
    ]
    list_filter = ["workflow", "public_access", "created_by__is_paying"]
    search_fields = ["workflow", "published_run_id", "title", "notes"]
    autocomplete_fields = ["saved_run", "created_by", "last_edited_by", "workspace"]
    readonly_fields = [
        "open_in_gooey",
        "view_runs",
        "run_count",
        "view_bot_integrations",
        "created_at",
        "updated_at",
    ]
    inlines = [PublishedRunVersionInline]

    def view_user(self, published_run: PublishedRun):
        if published_run.created_by is None:
            return None
        return change_obj_url(published_run.created_by)

    view_user.short_description = "View User"

    def linked_saved_run(self, published_run: PublishedRun):
        return change_obj_url(published_run.saved_run)

    linked_saved_run.short_description = "Linked Run"

    @admin.display(description="View Runs")
    def view_runs(self, published_run: PublishedRun):
        return list_related_html_url(
            SavedRun.objects.filter(parent_version__published_run=published_run),
            query_param="parent_version__published_run__id__exact",
            instance_id=published_run.id,
            show_add=False,
        )

    @admin.display(description="Bot Integrations")
    def view_bot_integrations(self, published_run: PublishedRun):
        return list_related_html_url(
            published_run.botintegrations.all(),
            query_param="published_run__id__exact",
            instance_id=published_run.id,
        )


@admin.register(SavedRun)
class SavedRunAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "run_id",
        "view_user",
        "open_in_gooey",
        "view_parent_published_run",
        "run_time",
        "price",
        "is_api_call",
        "created_at",
        "updated_at",
        "run_status",
        "error_msg",
    ]
    list_filter = [
        "workflow",
        "is_api_call",
        "is_flagged",
        ("run_status", admin.EmptyFieldListFilter),
        ("error_msg", admin.EmptyFieldListFilter),
        "created_at",
        "retention_policy",
    ]
    search_fields = ["workflow", "example_id", "run_id", "uid"]
    autocomplete_fields = ["parent_version", "workspace"]

    readonly_fields = [
        "open_in_gooey",
        "view_parent_published_run",
        "view_bots",
        "price",
        "view_usage_cost",
        "transaction",
        "parent",
        "created_at",
        "updated_at",
        "run_time",
        "is_api_call",
    ]

    actions = [export_to_csv, export_to_excel, "rerun_tasks"]

    formfield_overrides = {
        django.db.models.JSONField: {"widget": JSONEditorWidget},
    }

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related(
                "parent_version",
                "parent_version__published_run",
                "parent_version__published_run__saved_run",
            )
        )

    def lookup_allowed(self, key, value):
        if key in ["parent_version__published_run__id__exact"]:
            return True
        return super().lookup_allowed(key, value)

    def view_user(self, saved_run: SavedRun):
        user = AppUser.objects.get(uid=saved_run.uid)
        return change_obj_url(user)

    view_user.short_description = "View User"

    def view_bots(self, saved_run: SavedRun):
        pr = saved_run.parent_published_run()
        if not pr:
            raise SavedRun.DoesNotExist
        return list_related_html_url(pr.botintegrations)

    view_bots.short_description = "View Bots"

    @admin.display(description="View Published Run")
    def view_parent_published_run(self, saved_run: SavedRun):
        pr = saved_run.parent_published_run()
        return pr and change_obj_url(pr)

    @admin.display(description="Usage Costs")
    def view_usage_cost(self, saved_run: SavedRun):
        total_cost = saved_run.usage_costs.aggregate(total_cost=Sum("dollar_amount"))[
            "total_cost"
        ]
        return list_related_html_url(
            saved_run.usage_costs, extra_label=f"${total_cost.normalize()}"
        )

    @admin.action(description="Re-Run Tasks")
    def rerun_tasks(self, request, queryset):
        sr: SavedRun
        for sr in queryset.all():
            page = Workflow(sr.workflow).page_cls(
                user=AppUser.objects.get(uid=sr.uid),
                query_params=dict(run_id=sr.run_id, uid=sr.uid),
            )
            page.call_runner_task(sr, deduct_credits=False)
        self.message_user(
            request,
            f"Started re-running {queryset.count()} tasks in the background.",
        )


class LastActiveDeltaFilter(admin.SimpleListFilter):
    title = Conversation.last_active_delta.short_description
    parameter_name = Conversation.last_active_delta.__name__

    def lookups(self, request, model_admin):
        return [
            (
                int(delta.total_seconds()),
                timesince(datetime.datetime.now() - delta),
            )
            for delta in [
                datetime.timedelta(days=7),
                datetime.timedelta(days=3),
                datetime.timedelta(days=1),
                datetime.timedelta(hours=12),
                datetime.timedelta(hours=1),
            ]
        ]

    def queryset(self, request, queryset):
        if self.value():
            queryset = queryset.filter(
                __last_active_delta__gt=datetime.timedelta(seconds=int(self.value()))
            )
        return queryset


class NullifyEmptyStringsModelForm(forms.ModelForm):
    def clean(self):
        cleaned_data = super().clean()
        for field in self._meta.model._meta.get_fields():
            if (
                hasattr(field, "null")
                and field.null
                and field.get_internal_type() in ["CharField", "TextField"]
            ):
                if cleaned_data.get(field.name) == "":
                    cleaned_data[field.name] = None
        return cleaned_data


class ConversationAdminForm(NullifyEmptyStringsModelForm):
    class Meta:
        model = Conversation
        fields = "__all__"


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = [
        "get_display_name",
        "view_messages",
        "d1",
        "d7",
        "d30",
        "view_last_msg",
        "bot_integration",
        "created_at",
        "view_last_active_delta",
    ]
    readonly_fields = [
        "created_at",
        "view_last_msg",
        "view_messages",
        "view_feedbacks",
    ]
    list_filter = ["bot_integration", "created_at", LastActiveDeltaFilter]
    autocomplete_fields = ["bot_integration"]
    search_fields = [
        "fb_page_id",
        "fb_page_name",
        "fb_page_access_token",
        "ig_account_id",
        "ig_username",
        "wa_phone_number",
        "slack_user_id",
        "slack_team_id",
        "slack_user_name",
        "slack_channel_id",
        "slack_channel_name",
        "twilio_phone_number",
    ] + [f"bot_integration__{field}" for field in BotIntegrationAdmin.search_fields]
    actions = [export_to_csv, export_to_excel]

    form = ConversationAdminForm

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(
            __last_msg=Max("messages__created_at"),
            __msg_count=Count("messages"),
            __last_active_delta=Max("messages__created_at") - F("created_at"),
        )
        return qs

    def view_last_msg(self, convo: Conversation):
        msg = convo.messages.latest()
        return change_obj_url(
            msg,
            label=f"{dateformat.format(msg.created_at, settings.DATETIME_FORMAT)}",
        )

    view_last_msg.short_description = "Last Message"
    view_last_msg.admin_order_field = "__last_msg"

    def view_messages(self, convo: Conversation):
        return list_related_html_url(convo.messages, show_add=False)

    view_messages.short_description = "Messages"
    view_messages.admin_order_field = "__msg_count"

    @admin.display(description="View Feedbacks")
    def view_feedbacks(self, convo: Conversation):
        return list_related_html_url(
            Feedback.objects.filter(message__conversation=convo),
            "message__conversation__id__exact",
            convo.id,
            show_add=False,
        )

    def view_last_active_delta(self, convo: Conversation):
        return timesince(datetime.datetime.now() - convo.last_active_delta())

    view_last_active_delta.short_description = "Duration"
    view_last_active_delta.admin_order_field = "__last_active_delta"


class FeedbackInline(admin.TabularInline):
    model = Feedback
    extra = 0
    can_delete = False
    readonly_fields = ["created_at"]


class MessageAttachmentInline(admin.TabularInline):
    model = MessageAttachment
    extra = 0
    readonly_fields = ["url", "metadata", "created_at"]


class AnalysisResultFilter(admin.SimpleListFilter):
    title = "analysis_result"
    parameter_name = "analysis_result"

    def lookups(self, request, model_admin):
        val = self.value()
        if val is None:
            return []
        k, v = json.loads(val)
        return [(val, f"{k[-1]} = {v}")]

    def queryset(self, request, queryset):
        val = self.value()
        if val is None:
            return queryset
        k, v = json.loads(val)
        return queryset.annotate(val=JSONBExtractPath(self.parameter_name, k)).filter(
            val=v
        )


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    autocomplete_fields = ["conversation"]
    list_filter = [
        "role",
        "conversation__bot_integration",
        "created_at",
        AnalysisResultFilter,
    ]
    search_fields = [
        "role",
        "content",
        "display_content",
        "platform_msg_id",
        "analysis_result",
    ] + [f"conversation__{field}" for field in ConversationAdmin.search_fields]
    list_display = [
        "__str__",
        "local_lang",
        "role",
        "created_at",
        "feedbacks",
        "msg_delivered",
    ]
    readonly_fields = [
        "conversation",
        "role",
        "content",
        "display_content",
        "created_at",
        "platform_msg_id",
        "saved_run",
        "analysis_run",
        "prev_msg_content",
        "prev_msg_display_content",
        "prev_msg_saved_run",
        "response_time",
    ]
    ordering = ["-created_at"]
    actions = [export_to_csv, export_to_excel]

    inlines = [MessageAttachmentInline, FeedbackInline]

    formfield_overrides = {
        django.db.models.JSONField: {"widget": JSONEditorWidget},
    }

    def feedbacks(self, msg: Message):
        return msg.feedbacks.count() or None

    feedbacks.short_description = "Feedbacks"

    def get_fieldsets(self, request, msg: Message = None):
        fieldsets = [
            (
                None,
                {
                    "fields": [
                        "conversation",
                        "role",
                        "created_at",
                        "platform_msg_id",
                    ]
                },
            ),
        ]
        if msg and msg.role == CHATML_ROLE_ASSISTANT:
            fieldsets.append(
                (
                    "User Message",
                    {
                        "fields": [
                            "prev_msg_content",
                            "prev_msg_display_content",
                            "prev_msg_saved_run",
                        ]
                    },
                )
            )
        fieldsets.append(
            (
                "Message",
                {
                    "fields": [
                        "content",
                        "display_content",
                        "saved_run",
                    ]
                },
            ),
        )
        fieldsets.append(
            (
                "Analysis",
                {
                    "fields": [
                        "response_time",
                        "analysis_result",
                        "analysis_run",
                        "question_answered",
                        "question_subject",
                    ]
                },
            )
        )
        return fieldsets

    def msg_delivered(self, msg: Message):
        if (
            # user messages are delivered already
            msg.role != CHATML_ROLE_ASSISTANT
            # we only have delivery status for whatsapp and slack
            or msg.conversation.bot_integration.platform
            not in [Platform.WHATSAPP, Platform.SLACK]
        ):
            raise Message.DoesNotExist
        return bool(msg.platform_msg_id)

    msg_delivered.short_description = "Delivered"
    msg_delivered.boolean = True

    def prev_msg_content(self, message: Message):
        prev_msg = message.get_previous_by_created_at()
        return change_obj_url(prev_msg, label=prev_msg.content)

    prev_msg_content.short_description = "User Message (English)"

    def prev_msg_display_content(self, message: Message):
        prev_msg = message.get_previous_by_created_at()
        return change_obj_url(prev_msg, label=prev_msg.display_content)

    prev_msg_display_content.short_description = "User Message (Original)"

    def prev_msg_saved_run(self, message: Message):
        prev_msg = message.get_previous_by_created_at()
        return change_obj_url(prev_msg.saved_run)

    prev_msg_saved_run.short_description = "Speech Run"


class FeedbackCommentInline(admin.StackedInline):
    model = FeedbackComment
    extra = 0
    readonly_fields = [
        "created_at",
    ]
    autocomplete_fields = ["author"]


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    autocomplete_fields = ["message"]
    list_filter = ["rating", "status", "message__conversation__bot_integration"]
    search_fields = (
        ["text", "text_english"]
        + [f"message__{field}" for field in MessageAdmin.search_fields]
        + [
            f"message__conversation__{field}"
            for field in ConversationAdmin.search_fields
        ]
    )
    list_display = [
        "__str__",
        "prev_msg",
        "msg",
        "text",
        "created_at",
        "conversation_link",
    ]
    readonly_fields = [
        "created_at",
        "prev_msg_content",
        "messsage_content",
        "prev_msg_display_content",
        "messsage_display_content",
        "conversation_link",
        "saved_run",
        "text_english",
        "rating",
    ]
    inlines = [FeedbackCommentInline]
    actions = [export_to_csv, export_to_excel]

    fieldsets = (
        (
            None,
            {
                "fields": [
                    "rating",
                    "conversation_link",
                    "saved_run",
                ]
            },
        ),
        (
            "English",
            {
                "fields": (
                    "prev_msg_content",
                    "messsage_content",
                    "text_english",
                ),
            },
        ),
        (
            "Localized",
            {
                "fields": (
                    "prev_msg_display_content",
                    "messsage_display_content",
                    "text",
                ),
            },
        ),
        (
            "Annotations",
            {
                "fields": ("category", "creator", "status"),
            },
        ),
    )

    def lookup_allowed(self, key, value):
        if key in ["message__conversation__id__exact"]:
            return True
        return super().lookup_allowed(key, value)

    @admin.display(description="User Message (English)")
    def prev_msg_content(self, feedback: Feedback):
        prev_msg = self.prev_msg(feedback)
        return change_obj_url(prev_msg, label=prev_msg.content)

    @admin.display(description="User Message (Original)")
    def prev_msg_display_content(self, feedback: Feedback):
        prev_msg = self.prev_msg(feedback)
        return change_obj_url(prev_msg, label=prev_msg.display_content)

    @admin.display(description="User Message")
    def prev_msg(self, feedback):
        return feedback.message.get_previous_by_created_at()

    @admin.display(description="Bot Response (English)")
    def messsage_content(self, feedback: Feedback):
        msg = self.msg(feedback)
        return change_obj_url(msg, label=msg.content)

    @admin.display(description="Bot Response (Original)")
    def messsage_display_content(self, feedback: Feedback):
        msg = self.msg(feedback)
        return change_obj_url(msg, label=msg.display_content)

    @admin.display(description="Bot Response")
    def msg(self, feedback: Feedback):
        return feedback.message

    @admin.display(description="Saved Run")
    def saved_run(self, feedback: Feedback):
        return change_obj_url(feedback.message.conversation.bot_integration.saved_run)

    def conversation_link(self, feedback: Feedback):
        return change_obj_url(
            feedback.message.conversation,
            label=f"View Conversation for {feedback.message.conversation.get_display_name()}",
        )

    conversation_link.short_description = "Conversation"


@admin.register(WorkflowMetadata)
class WorkflowMetadataAdmin(admin.ModelAdmin):
    list_display = [
        "workflow",
        "short_title",
        "meta_title",
        "meta_description",
        "created_at",
        "updated_at",
        "price_multiplier",
        "emoji",
    ]
    search_fields = ["workflow", "meta_title", "meta_description"]
    list_filter = ["workflow"]
    readonly_fields = ["created_at", "updated_at"]
