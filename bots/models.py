from django.db import models, transaction
from django.db.models import Q
from django.utils.text import Truncator
from phonenumber_field.modelfields import PhoneNumberField

from daras_ai_v2.all_pages import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.language_model import CHATML_ROLE_USER, CHATML_ROLE_ASSISSTANT
from gooeysite.custom_fields import CustomURLField


class Platform(models.IntegerChoices):
    FACEBOOK = 1
    INSTAGRAM = (2, "Instagram & FB")
    WHATSAPP = 3

    def get_favicon(self):
        if self == Platform.WHATSAPP:
            return f"https://static.facebook.com/images/whatsapp/www/favicon.png"
        else:
            return f"https://www.{self.name.lower()}.com/favicon.ico"


class SavedRun(models.Model):
    workflow = models.IntegerField(choices=Workflow.choices, default=Workflow.VIDEOBOTS)
    example_id = models.TextField(
        default="",
        blank=True,
    )
    run_id = models.TextField(
        default="",
        blank=True,
    )
    uid = models.TextField(
        default="",
        blank=True,
    )

    class Meta:
        unique_together = ["workflow", "example_id", "run_id", "uid"]
        indexes = [
            models.Index(fields=["workflow", "example_id", "run_id", "uid"]),
            models.Index(fields=["workflow"]),
            models.Index(fields=["run_id", "uid"]),
            models.Index(fields=["example_id"]),
        ]

    def __str__(self):
        return self.get_app_url()

    def get_app_url(self):
        page_cls = Workflow(self.workflow).page_cls
        return page_cls.app_url(self.example_id, self.run_id, self.uid)

    def get_firebase_url(self):
        """return the url to the firebase dashboard for the document daras-ai-v2/workflow/example_id or daras-ai-v2/workflow or daras-ai-v2/uid/run_id"""
        page = Workflow(self.workflow).page_cls()
        if self.run_id and self.uid:
            ref = page.run_doc_ref(self.uid, self.run_id)
        elif self.example_id:
            ref = page.example_doc_ref(self.example_id)
        else:
            ref = page.recipe_doc_ref()
        return (
            "https://console.firebase.google.com/project/dara-c1b52/firestore/data/"
            + ref.path
        )


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
        max_length=1024, help_text="The name of the bot (for display purposes)"
    )
    saved_run = models.ForeignKey(
        "bots.SavedRun",
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
        default="en",
        help_text="The response language (same as user language in video bots)",
    )
    show_feedback_buttons = models.BooleanField(
        default=False, help_text="Show 👍/👎 buttons with every response"
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
        help_text="Bot's Facebook page id (required if platform is Facebook/Instagram)",
    )
    fb_page_name = models.TextField(
        default="",
        blank=True,
        help_text="Bot's Facebook page name (only for display)",
    )
    fb_page_access_token = models.TextField(
        blank=True,
        default="",
        help_text="Bot's Facebook page access token (required if platform is Facebook/Instagram)",
        editable=False,
    )
    ig_account_id = models.CharField(
        max_length=256,
        blank=True,
        default=None,
        null=True,
        unique=True,
        help_text="Bot's Instagram account id (required if platform is Instagram)",
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
        help_text="Bot's WhatsApp phone number id (required if platform is WhatsApp)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BotIntegrationQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["billing_account_uid", "platform"]),
            models.Index(fields=["fb_page_id", "ig_account_id", "wa_phone_number_id"]),
        ]

    def __str__(self):
        return f"{self.name or self.wa_phone_number or self.ig_username or self.fb_page_name}"


class Conversation(models.Model):
    bot_integration = models.ForeignKey(
        "BotIntegration", on_delete=models.CASCADE, related_name="conversations"
    )

    fb_page_id = models.TextField(
        blank=True,
        default="",
        db_index=True,
        help_text="User's Facebook page id (required if platform is Facebook/Instagram)",
    )
    fb_page_name = models.TextField(
        default="",
        blank=True,
        help_text="User's Facebook page name (only for display)",
    )
    fb_page_access_token = models.TextField(
        blank=True,
        default="",
        help_text="User's Facebook page access token (required if platform is Facebook/Instagram)",
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
        help_text="User's WhatsApp phone number (only for display)",
    )
    wa_phone_number_id = models.TextField(
        blank=True,
        default="",
        db_index=True,
        help_text="User's WhatsApp phone number id (required if platform is WhatsApp)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=[
                    "bot_integration",
                    "fb_page_id",
                    "ig_account_id",
                    "wa_phone_number_id",
                ]
            ),
        ]

    def __str__(self):
        display_name = (
            (self.wa_phone_number and self.wa_phone_number.as_international)
            or self.ig_username
            or self.fb_page_name
        )
        return f"{display_name} <> {self.bot_integration}"


class Message(models.Model):
    conversation = models.ForeignKey(
        "Conversation", on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(
        choices=(
            # ("system", "System"),
            (CHATML_ROLE_USER, "User"),
            (CHATML_ROLE_ASSISSTANT, "Asisstant"),
        ),
        max_length=10,
    )
    content = models.TextField()

    saved_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.SET_NULL,
        related_name="messages",
        null=True,
        blank=True,
        default=None,
        help_text="The saved run that generated this message",
    )

    wa_msg_id = models.TextField(
        blank=True,
        default="",
        help_text="WhatsApp message id (required if platform is WhatsApp)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        get_latest_by = "created_at"
        indexes = [models.Index(fields=["conversation", "-created_at"])]

    def __str__(self):
        return f"{self.role} - {Truncator(self.content).words(10)}"


class Feedback(models.Model):
    message = models.ForeignKey(
        "Message", on_delete=models.CASCADE, related_name="feedbacks"
    )

    RATING_THUMBS_UP = 1
    RATING_THUMBS_DOWN = 2

    rating = models.IntegerField(
        choices=(
            (RATING_THUMBS_UP, "👍🏾"),
            (RATING_THUMBS_DOWN, "👎🏾"),
        ),
    )
    text = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self):
        return f"{self.get_rating_display()} - {Truncator(self.text).words(10)}"
