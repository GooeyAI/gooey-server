from __future__ import annotations

import datetime
import typing
from collections import defaultdict

import phonenumber_field.modelfields
import pytz
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import OuterRef, Q, QuerySet, Subquery
from django.utils.text import Truncator

from bots.custom_fields import CustomURLField
from daras_ai_v2.language_model import (
    CHATML_ROLE_ASSISTANT,
    CHATML_ROLE_USER,
    ConversationEntry,
    format_chat_entry,
)

from .bot_integration import WhatsappPhoneNumberField

if typing.TYPE_CHECKING:
    import pandas as pd


class ConvoBlockedStatus(models.IntegerChoices):
    NORMAL = 0, "Normal"
    WARNING = 1, "Warning"
    BLOCKED = 2, "Blocked"


class ConversationQuerySet(models.QuerySet):
    def distinct_by_user_id(self) -> QuerySet["Conversation"]:
        """Get unique conversations"""
        return self.distinct(*Conversation.user_id_fields)

    def to_df(
        self, tz=pytz.timezone(settings.TIME_ZONE), row_limit=1000
    ) -> pd.DataFrame:
        import pandas as pd

        qs = self.all().select_related("bot_integration")
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
                    feedbacks__rating=Feedback.Rating.POSITIVE
                ).count(),
                "Thumbs down": convo.messages.filter(
                    feedbacks__rating=Feedback.Rating.NEGATIVE
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
                    "A7": (
                        last_time > datetime.datetime.now() - datetime.timedelta(days=7)
                    ),
                    "A30": (
                        last_time
                        > datetime.datetime.now() - datetime.timedelta(days=30)
                    ),
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
                "Created At": (
                    convo.created_at.astimezone(tz)
                    .replace(tzinfo=None)
                    .strftime(settings.SHORT_DATETIME_FORMAT)
                ),
                "Integration Name": convo.bot_integration.name,
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
                "Integration Name",
            ],
        )
        return df


class Conversation(models.Model):
    bot_integration = models.ForeignKey(
        "BotIntegration", on_delete=models.CASCADE, related_name="conversations"
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

    blocked_status = models.IntegerField(
        choices=ConvoBlockedStatus.choices,
        default=ConvoBlockedStatus.NORMAL,
    )
    blocked_at = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        help_text="Timestamp when the conversation was blocked.",
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
        try:
            latest = self.messages.latest()
        except Message.DoesNotExist:
            return datetime.timedelta(0)
        return abs(latest.created_at - self.created_at)

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

    def last_n_msgs_as_entries(self) -> list["ConversationEntry"]:
        return self.messages.all().last_n_msgs_as_entries(reset_at=self.reset_at)

    def last_n_msgs(self) -> list["Message"]:
        return self.messages.all().last_n_msgs(reset_at=self.reset_at)

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
    ) -> pd.DataFrame:
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
                "Credits Used": row.get("credits_used", 0),
                "Run URL": row.get("run_url"),
                "Input Images": ", ".join(row.get("input_images") or []),
                "Input Audio": row.get("input_audio"),
                "User Message ID": row.get("user_message_id"),
                "Conversation ID": row.get("conversation_id"),
                "Integration Name": row.get("integration_name"),
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
            "feedbacks", "conversation", "saved_run", "conversation__bot_integration"
        )
        for message in qs[:row_limit]:
            message: Message
            rows = conversations[message.conversation_id]

            # since we've sorted by -created_at, we'll get alternating assistant and user messages
            if message.role == CHATML_ROLE_ASSISTANT:
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
                    row["credits_used"] = saved_run.price or 0
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
                        "integration_name": message.conversation.bot_integration.name,
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

    def last_n_msgs_as_entries(
        self, n: int = 50, reset_at: datetime.datetime = None
    ) -> list["ConversationEntry"]:
        return db_msgs_to_entries(self.last_n_msgs(n, reset_at))

    def last_n_msgs(
        self, n: int = 50, reset_at: datetime.datetime = None
    ) -> list["Message"]:
        if reset_at:
            self = self.filter(created_at__gt=reset_at)
        msgs = self.order_by("-created_at").prefetch_related("attachments")[:n]
        return list(reversed(msgs))


def db_msgs_to_entries(msgs: list["Message"]) -> list["ConversationEntry"]:
    entries = [None] * len(msgs)
    for i, msg in enumerate(msgs):
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
            (CHATML_ROLE_ASSISTANT, "Bot"),
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


def db_msgs_to_api_json(msgs: list["Message"]) -> typing.Iterator[dict]:
    from daras_ai_v2.bots import parse_bot_html
    from routers.bots_api import MSG_ID_PREFIX

    for msg in msgs:
        msg: Message
        images = list(
            msg.attachments.filter(
                metadata__mime_type__startswith="image/"
            ).values_list("url", flat=True)
        )
        audios = list(
            msg.attachments.filter(
                metadata__mime_type__startswith="audio/"
            ).values_list("url", flat=True)
        )
        audio = audios and audios[0]
        if msg.role == CHATML_ROLE_USER:
            # any document type other than audio/image
            documents = list(
                msg.attachments.exclude(
                    Q(metadata__mime_type__startswith="image/")
                    | Q(metadata__mime_type__startswith="audio/")
                ).values_list("url", flat=True)
            )
            yield {
                "role": msg.role,
                "input_prompt": msg.display_content or msg.content,
                "input_images": images,
                "input_audio": audio,
                "input_documents": documents,
                "created_at": msg.created_at.isoformat(),
            }
        elif msg.role == CHATML_ROLE_ASSISTANT:
            saved_run = msg.saved_run
            references = []
            web_url = ""
            if saved_run:
                references = saved_run.state.get("references") or []
                web_url = saved_run.get_app_url()
            buttons, text = parse_bot_html(msg.display_content)[:2]
            yield {
                "role": msg.role,
                "created_at": msg.created_at.isoformat(),
                "status": "completed",
                "type": "final_response",
                "raw_output_text": [msg.content],
                "output_text": [text],
                "buttons": buttons,
                "output_images": images,
                "output_audio": audio,
                "web_url": web_url,
                "user_message_id": msg.platform_msg_id,
                "bot_message_id": (
                    msg.platform_msg_id
                    and msg.platform_msg_id.removeprefix(MSG_ID_PREFIX)
                ),
                "references": references,
            }


class FeedbackQuerySet(models.QuerySet):
    def to_df(
        self, tz=pytz.timezone(settings.TIME_ZONE), row_limit=10000
    ) -> pd.DataFrame:
        import pandas as pd

        qs = self.all().prefetch_related(
            "message", "message__conversation", "message__conversation__bot_integration"
        )
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
                "Integration Name": feedback.message.conversation.bot_integration.name,
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
                "Integration Name",
            ],
        )
        return df


class Feedback(models.Model):
    message = models.ForeignKey(
        "Message", on_delete=models.CASCADE, related_name="feedbacks"
    )

    class Rating(models.IntegerChoices):
        POSITIVE = 1, "👍🏾"
        NEGATIVE = 2, "👎🏾"
        NEUTRAL = 3, "🤔"

    rating = models.IntegerField(choices=Rating.choices)
    text = models.TextField(
        blank=True, default="", verbose_name="Feedback Text (Original)"
    )
    text_english = models.TextField(
        blank=True, default="", verbose_name="Feedback Text (English)"
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
