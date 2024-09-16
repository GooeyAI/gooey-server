import typing

from django.db.models import Q
from fastapi import Depends
from fastapi import HTTPException
from pydantic import BaseModel, Field

from app_users.models import AppUser
from auth.token_authentication import api_auth_header
from bots.models import BotIntegration
from bots.tasks import send_broadcast_msgs_chunked
from recipes.VideoBots import ReplyButton, VideoBotsPage
from routers.custom_api_router import CustomAPIRouter

app = CustomAPIRouter()


class BotBroadcastFilters(BaseModel):
    wa_phone_number__in: list[str] | None = Field(
        description="A list of WhatsApp phone numbers to broadcast to."
    )
    slack_user_id__in: list[str] | None = Field(
        description="A list of Slack user IDs to broadcast to."
    )
    slack_user_name__icontains: str | None = Field(
        description="Filter by the Slack user's name. Case insensitive."
    )
    slack_channel_is_personal: bool | None = Field(
        description="Filter by whether the Slack channel is personal. By default, will broadcast to both public and personal slack channels."
    )


class BotBroadcastRequestModel(BaseModel):
    text: str = Field(description="Message to broadcast to all users")
    audio: str | None = Field(description="Audio URL to send to all users")
    video: str | None = Field(description="Video URL to send to all users")
    documents: list[str] | None = Field(description="Video URL to send to all users")
    buttons: list[ReplyButton] | None = Field(
        description="Buttons to send to all users"
    )
    filters: BotBroadcastFilters | None = Field(
        description="Filters to select users to broadcast to. If not provided, will broadcast to all users of this bot."
    )


R = typing.TypeVar("R", bound=BotBroadcastRequestModel)


@app.post(
    f"/v2/{VideoBotsPage.slug_versions[0]}/broadcast/send/",
    operation_id=VideoBotsPage.slug_versions[0] + "__broadcast",
    tags=["Misc"],
    name=f"Send Broadcast Message",
)
@app.post(
    f"/v2/{VideoBotsPage.slug_versions[0]}/broadcast/send",
    include_in_schema=False,
)
def broadcast_api_json(
    bot_request: BotBroadcastRequestModel,
    user: AppUser = Depends(api_auth_header),
    example_id: str | None = None,
    run_id: str | None = None,
):
    bi_qs = BotIntegration.objects.filter(billing_account_uid=user.uid)
    if example_id:
        bi_qs = bi_qs.filter(
            Q(published_run__published_run_id=example_id)
            | Q(saved_run__example_id=example_id)
        )
    elif run_id:
        bi_qs = bi_qs.filter(saved_run__run_id=run_id, saved_run__uid=user.uid)
    else:
        return HTTPException(
            status_code=400,
            detail="Must provide either example_id or run_id as a query parameter.",
        )
    if not bi_qs.exists():
        return HTTPException(
            status_code=404,
            detail=f"Could not find a bot in your account with the given {example_id=} & {run_id=}. "
            "Please use the same account that you used to create the bot.",
        )

    total = 0
    for bi in bi_qs:
        convo_qs = bi.conversations.all()
        if bot_request.filters:
            convo_qs = convo_qs.filter(**bot_request.filters.dict(exclude_unset=True))
        total += convo_qs.count()
        send_broadcast_msgs_chunked(
            text=bot_request.text,
            audio=bot_request.audio,
            video=bot_request.video,
            documents=bot_request.documents,
            buttons=bot_request.buttons,
            bi=bi,
            convo_qs=convo_qs,
        )

    return {"status": "success", "count": total}
