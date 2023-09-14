import datetime
import typing
from multiprocessing.pool import ThreadPool

import pytz
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models import Q
from django.utils.text import Truncator
from furl import furl
from phonenumber_field.modelfields import PhoneNumberField

from app_users.models import AppUser
from bots.custom_fields import PostgresJSONEncoder

if typing.TYPE_CHECKING:
    from daras_ai_v2.base import BasePage
    import celery.result

CHATML_ROLE_USER = "user"
CHATML_ROLE_ASSISSTANT = "assistant"


EPOCH = datetime.datetime.utcfromtimestamp(0)


class Platform(models.IntegerChoices):
    FACEBOOK = 1
    INSTAGRAM = (2, "Instagram & FB")
    WHATSAPP = 3
    SLACK = 4

    def get_favicon(self):
        if self == Platform.WHATSAPP:
            return f"https://static.facebook.com/images/whatsapp/www/favicon.png"
        else:
            return f"https://www.{self.name.lower()}.com/favicon.ico"


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
    COMPARE_UPSCALER = (15, "Comapre AI Upscalers")
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

    @property
    def short_slug(self):
        return min(self.page_cls.slug_versions, key=len)

    def get_app_url(self, example_id: str, run_id: str, uid: str):
        """return the url to the gooey app"""
        query_params = {}
        if run_id and uid:
            query_params |= dict(run_id=run_id, uid=uid)
        if example_id:
            query_params |= dict(example_id=example_id)
        return str(
            furl(settings.APP_BASE_URL, query_params=query_params)
            / self.short_slug
            / "/"
        )

    @property
    def page_cls(self) -> typing.Type["BasePage"]:
        from daras_ai_v2.all_pages import workflow_map

        return workflow_map[self]


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


class SavedRun(models.Model):
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )

    workflow = models.IntegerField(
        choices=Workflow.choices, default=Workflow.VIDEO_BOTS
    )
    example_id = models.CharField(max_length=128, default=None, null=True, blank=True)
    run_id = models.CharField(max_length=128, default=None, null=True, blank=True)
    uid = models.CharField(max_length=128, default=None, null=True, blank=True)

    state = models.JSONField(default=dict, blank=True, encoder=PostgresJSONEncoder)

    error_msg = models.TextField(default="", blank=True)
    run_time = models.DurationField(default=datetime.timedelta, blank=True)
    run_status = models.TextField(default="", blank=True)
    page_title = models.TextField(default="", blank=True)
    page_notes = models.TextField(default="", blank=True)
    hidden = models.BooleanField(default=False)
    is_flagged = models.BooleanField(default=False)

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = SavedRunQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        unique_together = [
            ["workflow", "example_id"],
            ["workflow", "run_id", "uid"],
        ]
        constraints = [
            models.CheckConstraint(
                # ensure that the parent is not the same as the current record
                check=~models.Q(parent=models.F("id")),
                name="parent_not_self",
            ),
        ]
        indexes = [
            models.Index(fields=["workflow"]),
            models.Index(fields=["workflow", "run_id", "uid"]),
            models.Index(fields=["workflow", "example_id", "run_id", "uid"]),
            models.Index(fields=["workflow", "example_id", "hidden"]),
            models.Index(fields=["workflow", "uid", "updated_at"]),
        ]

    def __str__(self):
        return self.get_app_url()

    def get_app_url(self):
        workflow = Workflow(self.workflow)
        return workflow.get_app_url(self.example_id, self.run_id, self.uid)

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
        if self.page_title:
            ret[StateKeys.page_title] = self.page_title
        if self.page_notes:
            ret[StateKeys.page_notes] = self.page_notes
        if self.hidden:
            ret[StateKeys.hidden] = self.hidden
        if self.is_flagged:
            ret["is_flagged"] = self.is_flagged
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
        self.page_title = state.pop(StateKeys.page_title, None) or ""
        self.page_notes = state.pop(StateKeys.page_notes, None) or ""
        # self.hidden = state.pop(StateKeys.hidden, False)
        self.is_flagged = state.pop("is_flagged", False)
        self.state = state

        return self

    def submit_api_call(
        self,
        *,
        current_user: AppUser,
        request_body: dict,
    ) -> tuple["celery.result.AsyncResult", "SavedRun"]:
        from routers.api import submit_api_call

        # run in a thread to avoid messing up threadlocals
        with ThreadPool(1) as pool:
            page, result, run_id, uid = pool.apply(
                submit_api_call,
                kwds=dict(
                    page_cls=Workflow(self.workflow).page_cls,
                    query_params=dict(
                        example_id=self.example_id, run_id=self.id, uid=self.uid
                    ),
                    user=current_user,
                    request_body=request_body,
                ),
            )
        return result, page.run_doc_sr(run_id, uid)


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
    slack_channel_id = models.CharField(
        max_length=256,
        blank=True,
        default=None,
        null=True,
        unique=True,
        help_text="Bot's Slack channel id (required if platform is Slack)",
    )
    slack_channel_hook_url = models.TextField(
        blank=True,
        default="",
        help_text="Bot's Slack channel hook url (required if platform is Slack)",
    )
    slack_access_token = models.TextField(
        blank=True,
        default="",
        help_text="Bot's Slack access token (required if platform is Slack)",
        editable=False,
    )

    analysis_run = models.ForeignKey(
        "bots.SavedRun",
        on_delete=models.SET_NULL,
        related_name="analysis_botintegrations",
        null=True,
        blank=True,
        default=None,
        help_text="If provided, the message content will be analyzed for this bot using this saved run",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BotIntegrationQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["billing_account_uid", "platform"]),
            models.Index(fields=["fb_page_id", "ig_account_id"]),
        ]

    def __str__(self):
        orig_name = (
            (self.wa_phone_number and self.wa_phone_number.as_international)
            or self.ig_username
            or self.fb_page_name
            or self.wa_phone_number_id
            or self.fb_page_id
        )
        if self.name and orig_name and self.name != orig_name:
            return f"{self.name} ({orig_name})"
        else:
            return self.name or orig_name


class ConvoState(models.IntegerChoices):
    INITIAL = 0, "Initial"
    ASK_FOR_FEEDBACK_THUMBS_UP = 1, "Ask for feedback (👍)"
    ASK_FOR_FEEDBACK_THUMBS_DOWN = 2, "Ask for feedback (👎)"


class ConversationQuerySet(models.QuerySet):
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
                    "D3": convo.d3(),
                }
            except Message.DoesNotExist:
                pass
            rows.append(row)
        df = pd.DataFrame.from_records(rows)
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
        db_index=True,
        help_text="User's WhatsApp phone number (required if platform is WhatsApp)",
    )
    slack_user_id = models.TextField(
        blank=True,
        default="",
        db_index=True,
        help_text="User's Slack ID (required if platform is Slack)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    objects = ConversationQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["bot_integration", "fb_page_id", "ig_account_id"]),
            models.Index(fields=["bot_integration", "wa_phone_number"]),
            models.Index(fields=["bot_integration", "slack_user_id"]),
        ]

    def __str__(self):
        return f"{self.get_display_name()} <> {self.bot_integration}"

    def get_display_name(self):
        return (
            (self.wa_phone_number and self.wa_phone_number.as_international)
            or self.ig_username
            or self.fb_page_name
            or self.fb_page_id
            or self.slack_user_id
        )

    get_display_name.short_description = "User"

    def last_active_delta(self) -> datetime.timedelta:
        return abs(self.messages.latest().created_at - self.created_at)

    last_active_delta.short_description = "Duration"

    def d1(self):
        return self.last_active_delta() > datetime.timedelta(days=1)

    d1.short_description = "D1"
    d1.boolean = True

    def d3(self):
        return self.last_active_delta() > datetime.timedelta(days=3)

    d3.short_description = "D3"
    d3.boolean = True


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

    wa_msg_id = models.TextField(
        blank=True,
        default="",
        help_text="WhatsApp message id (required if platform is WhatsApp)",
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

    _analysis_started = False

    objects = MessageQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        get_latest_by = "created_at"
        indexes = [models.Index(fields=["conversation", "-created_at"])]

    def __str__(self):
        return Truncator(self.content).words(30)

    def local_lang(self):
        return Truncator(self.display_content).words(30)


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

    class Meta:
        ordering = ("-created_at",)
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
