from django import forms
from django.contrib import admin

from bots import models
from gooeysite.admin_links import list_related_html_url, open_in_new_tab


class BotIntegrationAdminForm(forms.ModelForm):
    class Meta:
        widgets = {
            "platform": forms.Select(
                attrs={
                    "--hideshow-fields": "fb_page_id,fb_page_name,fb_page_access_token,ig_account_id,ig_username,wa_phone_number,wa_phone_number_id",
                    "--show-on-1": "fb_page_id,fb_page_name,fb_page_access_token",
                    "--show-on-2": "fb_page_id,fb_page_name,fb_page_access_token,ig_account_id,ig_username",
                    "--show-on-3": "wa_phone_number,wa_phone_number_id",
                },
            ),
        }

    class Media:
        js = [
            "https://cdn.jsdelivr.net/gh/scientifichackers/django-hideshow@0.0.1/hideshow.js",
        ]


@admin.register(models.SavedRun)
class SavedRunAdmin(admin.ModelAdmin):
    search_fields = ["workflow", "example_id", "run_id", "uid", "view_in_firebase"]
    readonly_fields = ["view_bots", "open_in_firebase", "open_in_gooey"]

    def view_bots(self, saved_run: models.SavedRun):
        return list_related_html_url(saved_run.botintegrations)

    view_bots.short_description = "View Bots"

    def open_in_firebase(self, saved_run: models.SavedRun):
        return open_in_new_tab(saved_run.get_firebase_url())

    open_in_firebase.short_description = "Open in Firebase"

    def open_in_gooey(self, saved_run: models.SavedRun):
        return open_in_new_tab(saved_run.get_app_url())

    open_in_gooey.short_description = "Open in Gooey"


@admin.register(models.BotIntegration)
class BotIntegrationAdmin(admin.ModelAdmin):
    autocomplete_fields = ["saved_run"]
    search_fields = [
        "name",
        "ig_account_id",
        "ig_username",
        "fb_page_id",
        "phone_number",
    ]
    form = BotIntegrationAdminForm
    readonly_fields = ["view_conversations", "created_at", "updated_at"]
    list_display = ["__str__", "platform", "wa_phone_number"]

    def view_conversations(self, bi: models.BotIntegration):
        return list_related_html_url(bi.conversations)

    view_conversations.short_description = "Messages"


@admin.register(models.Conversation)
class ConversationAdmin(admin.ModelAdmin):
    autocomplete_fields = ["bot_integration"]
    search_fields = ["bot_integration", "user_phone_number"]
    readonly_fields = ["view_messages", "created_at"]

    def view_messages(self, convo: models.Conversation):
        return list_related_html_url(convo.messages)

    view_messages.short_description = "Messages"


class FeedbackInline(admin.TabularInline):
    model = models.Feedback
    extra = 0
    can_delete = False
    readonly_fields = ["created_at"]


@admin.register(models.Message)
class MessageAdmin(admin.ModelAdmin):
    autocomplete_fields = ["conversation"]
    search_fields = ["conversation", "role", "content"]
    readonly_fields = [
        "conversation",
        "role",
        "content",
        "created_at",
        "wa_msg_id",
        "saved_run",
    ]
    list_display = ["__str__", "role", "created_at", "feedbacks"]
    ordering = ["-created_at"]

    inlines = [FeedbackInline]

    def feedbacks(self, msg: models.Message):
        return msg.feedbacks.count() or None

    feedbacks.short_description = "Feedbacks"


@admin.register(models.Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    autocomplete_fields = ["message"]
    readonly_fields = ["created_at"]
