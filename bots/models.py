from django.db import models, transaction
from django.db.models import Q
from django.utils.text import Truncator
from phonenumber_field.modelfields import PhoneNumberField

from gooeysite.custom_fields import CustomURLField


class Platform(models.IntegerChoices):
    FACEBOOK = 1
    INSTAGRAM = (2, "Instagram & FB")
    WHATSAPP = 3


class BotIntegrationQuerySet(models.QuerySet):
    @transaction.atomic()
    def reset_fb_pages_for_user(self, uid: str, fb_pages: list[dict]):
        saved_ids = []
        for fb_page in fb_pages:
            # save to db / update exiting
            try:
                bi = BotIntegration.objects.get(fb_page_id=fb_page["id"])
            except BotIntegration.DoesNotExist:
                bi = BotIntegration(fb_page_id=fb_page["id"])
            bi.billing_account_uid = uid
            bi.fb_page_name = fb_page["name"]
            # bi.fb_user_access_token = user_access_token
            bi.fb_page_access_token = fb_page["access_token"]
            bi.ig_account_id = fb_page.get("instagram_business_account", {}).get("id")
            bi.ig_username = fb_page.get("instagram_business_account", {}).get(
                "username"
            )
            if bi.ig_username:
                bi.name = bi.ig_username + " & " + bi.fb_page_name
                bi.platform = Platform.INSTAGRAM
            else:
                bi.platform = Platform.FACEBOOK
                bi.name = bi.fb_page_name
            bi.save()
            saved_ids.append(bi.id)
        # delete pages that are no longer connected for this user
        self.filter(
            billing_account_uid=uid,
            platform=Q(Platform.FACEBOOK) | Q(Platform.INSTAGRAM),
        ).exclude(
            id__in=saved_ids,
        ).delete()


class BotIntegration(models.Model):
    name = models.CharField(
        max_length=1024, help_text="The name of the bot (for display purposes)"
    )
    app_url = CustomURLField(
        help_text="The gooey run url / example url / recipe url of the bot"
    )
    billing_account_uid = models.TextField(
        help_text="The gooey account uid where the credits will be deducted from",
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
        db_index=True,
        help_text="The platform that the bot is integrated with",
    )
    fb_page_id = models.TextField(
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
    ig_account_id = models.TextField(
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
    wa_phone_number_id = models.TextField(
        blank=True,
        default=None,
        null=True,
        unique=True,
        help_text="Bot's WhatsApp phone number id (required if platform is WhatsApp)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BotIntegrationQuerySet.as_manager()

    def __str__(self):
        return f"{self.name or self.wa_phone_number or self.ig_username or self.fb_page_name} ({self.get_platform_display()})"


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

    # class Meta:
    #     unique_together = ("bot_integration", "user_id")

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
            ("user", "User"),
            ("asisstant", "Asisstant"),
        ),
        max_length=10,
    )
    content = models.TextField()
    app_url = CustomURLField(editable=False, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)

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
