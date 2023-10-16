import datetime

import django.db.models
from django import forms
from django.conf import settings
from django.contrib import admin
from django.db.models import Max, Count, F
from django.http import HttpResponse
from django.template import loader
from django.utils import dateformat
from django.utils.safestring import mark_safe
from django.utils.timesince import timesince

from bots.admin_links import list_related_html_url, open_in_new_tab, change_obj_url
from bots.models import (
    FeedbackComment,
    CHATML_ROLE_ASSISSTANT,
    SavedRun,
    Message,
    Platform,
    Feedback,
    Conversation,
    BotIntegration,
)
from bots.tasks import create_personal_channels_for_all_members
from gooeysite.custom_filters import (
    related_json_field_summary,
)
from gooeysite.custom_widgets import JSONEditorWidget


@admin.action(description="Export to CSV")
def export_to_csv(
    modeladmin,
    request,
    queryset,
):
    filename = _get_filename()
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
    queryset.to_df().to_csv(response, index=False)
    return response


@admin.action(description="Export to Excel")
def export_to_excel(
    modeladmin,
    request,
    queryset,
):
    filename = _get_filename()
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
    queryset.to_df().to_excel(response, index=False)
    return response


def _get_filename():
    filename = f"Gooey.AI Table {dateformat.format(datetime.datetime.now(), settings.DATETIME_FORMAT)}"
    return filename


class BotIntegrationAdminForm(forms.ModelForm):
    class Meta:
        model = BotIntegration
        fields = "__all__"
        widgets = {
            "platform": forms.Select(
                attrs={
                    "--hideshow-fields": "fb_page_id,fb_page_name,fb_page_access_token,ig_account_id,ig_username,wa_phone_number,wa_phone_number_id,slack_team_id,slack_team_name,slack_channel_id,slack_channel_name,slack_channel_hook_url,slack_access_token,slack_read_receipt_msg,slack_create_personal_channels",
                    "--show-on-1": "fb_page_id,fb_page_name,fb_page_access_token",
                    "--show-on-2": "fb_page_id,fb_page_name,fb_page_access_token,ig_account_id,ig_username",
                    "--show-on-3": "wa_phone_number,wa_phone_number_id",
                    "--show-on-4": "slack_team_id,slack_team_name,slack_channel_id,slack_channel_name,slack_channel_hook_url,slack_access_token,slack_read_receipt_msg,slack_create_personal_channels",
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


@admin.register(BotIntegration)
class BotIntegrationAdmin(admin.ModelAdmin):
    search_fields = [
        "name",
        "billing_account_uid",
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
    ]
    list_display = [
        "name",
        "get_display_name",
        "platform",
        "wa_phone_number",
        "created_at",
        "updated_at",
        "billing_account_uid",
        "saved_run",
        "analysis_run",
    ]
    list_filter = ["platform"]

    form = BotIntegrationAdminForm

    autocomplete_fields = ["saved_run", "analysis_run"]

    readonly_fields = [
        "fb_page_access_token",
        "slack_access_token",
        "slack_channel_hook_url",
        "view_analysis_results",
        "view_conversations",
        "view_messsages",
        "created_at",
        "updated_at",
    ]

    fieldsets = [
        (
            None,
            {
                "fields": [
                    "name",
                    "saved_run",
                    "billing_account_uid",
                    "user_language",
                ],
            },
        ),
        (
            "Platform",
            {
                "fields": [
                    "platform",
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
                    "slack_read_receipt_msg",
                    "slack_create_personal_channels",
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
                    "show_feedback_buttons",
                    "analysis_run",
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
        )
        html = loader.render_to_string(
            "anaylsis_result.html", context=dict(results=results)
        )
        html = mark_safe(html)
        return html


@admin.register(SavedRun)
class SavedRunAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "example_id",
        "run_id",
        "uid",
        "created_at",
        "run_time",
        "updated_at",
        "price",
    ]
    list_filter = ["workflow"]
    search_fields = ["workflow", "example_id", "run_id", "uid"]

    readonly_fields = [
        "open_in_gooey",
        "parent",
        "view_bots",
        "price",
        "transaction",
        "created_at",
        "updated_at",
        "run_time",
    ]

    actions = [export_to_csv, export_to_excel]

    formfield_overrides = {
        django.db.models.JSONField: {"widget": JSONEditorWidget},
    }

    def view_bots(self, saved_run: SavedRun):
        return list_related_html_url(saved_run.botintegrations)

    view_bots.short_description = "View Bots"


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


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = [
        "get_display_name",
        "bot_integration",
        "created_at",
        "view_last_msg",
        "view_messages",
        "view_last_active_delta",
        "d1",
        "d3",
    ]
    readonly_fields = [
        "created_at",
        "view_last_msg",
        "view_messages",
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
    ] + [f"bot_integration__{field}" for field in BotIntegrationAdmin.search_fields]
    actions = [export_to_csv, export_to_excel]

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

    def view_last_active_delta(self, convo: Conversation):
        return timesince(datetime.datetime.now() - convo.last_active_delta())

    view_last_active_delta.short_description = "Duration"
    view_last_active_delta.admin_order_field = "__last_active_delta"


class FeedbackInline(admin.TabularInline):
    model = Feedback
    extra = 0
    can_delete = False
    readonly_fields = ["created_at"]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    autocomplete_fields = ["conversation"]
    list_filter = [
        "role",
        "conversation__bot_integration",
        "created_at",
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
    ]
    ordering = ["created_at"]
    actions = [export_to_csv, export_to_excel]

    inlines = [FeedbackInline]

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
        if msg and msg.role == CHATML_ROLE_ASSISSTANT:
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
            msg.role != CHATML_ROLE_ASSISSTANT
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
        "prev_msg_content",
        "text",
    ]
    readonly_fields = [
        "created_at",
        "prev_msg_content",
        "messsage_content",
        "prev_msg_display_content",
        "messsage_display_content",
        "conversation_link",
        "run_id",
        "text_english",
        "rating",
    ]
    inlines = [FeedbackCommentInline]

    fieldsets = (
        (
            None,
            {
                "fields": [
                    "rating",
                    "conversation_link",
                    "run_id",
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

    def prev_msg_content(self, feedback: Feedback):
        prev_msg = feedback.message.get_previous_by_created_at()
        return change_obj_url(prev_msg, label=prev_msg.content)

    prev_msg_content.short_description = "User Message (English)"

    def prev_msg_display_content(self, feedback: Feedback):
        prev_msg = feedback.message.get_previous_by_created_at()
        return change_obj_url(prev_msg, label=prev_msg.display_content)

    prev_msg_display_content.short_description = "User Message (Original)"

    def run_id(self, feedback: Feedback):
        return change_obj_url(feedback.message.conversation.bot_integration.saved_run)

    def conversation_link(self, feedback: Feedback):
        return change_obj_url(
            feedback.message.conversation,
            label=f"View Conversation for {feedback.message.conversation.get_display_name()}",
        )

    conversation_link.short_description = "Conversation"

    def messsage_content(self, feedback: Feedback):
        return change_obj_url(feedback.message, label=feedback.message.content)

    messsage_content.short_description = "Bot Response (English)"

    def messsage_display_content(self, feedback: Feedback):
        return change_obj_url(feedback.message, label=feedback.message.display_content)

    messsage_display_content.short_description = "Bot Response (Original)"
