import typing

from django.db.models import Q, QuerySet
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from api_keys.models import ApiKey
from auth.token_authentication import api_auth_header
from bots.models import BotIntegration, Conversation, Platform
from bots.tasks import (
    send_broadcast_msgs_chunked,
)
from daras_ai_v2.slack_bot import create_personal_channel, fetch_user_info
from recipes.VideoBots import ReplyButton, VideoBotsPage
from routers.custom_api_router import CustomAPIRouter

app = CustomAPIRouter()


class BotBroadcastFilters(BaseModel):
    twilio_phone_number__in: list[str] | None = Field(
        None, description="A list of Twilio phone numbers to broadcast to."
    )
    wa_phone_number__in: list[str] | None = Field(
        None, description="A list of WhatsApp phone numbers to broadcast to."
    )
    slack_user_id__in: list[str] | None = Field(
        None, description="A list of Slack user IDs to broadcast to."
    )
    slack_user_name__icontains: str | None = Field(
        None, description="Filter by the Slack user's name. Case insensitive."
    )
    slack_channel_is_personal: bool | None = Field(
        None,
        description="Filter by whether the Slack channel is personal. By default, will broadcast to public slack channels only.",
    )


class BotBroadcastRequestModel(BaseModel):
    text: str = Field(description="Message to broadcast to all users")
    audio: str | None = Field(None, description="Audio URL to send to all users")
    video: str | None = Field(None, description="Video URL to send to all users")
    documents: list[str] | None = Field(
        None, description="Video URL to send to all users"
    )
    integration_id: str | None = Field(
        description="The Bot's Integration ID as shown in the Copilot Integrations tab or as variables in a function call."
    )
    buttons: list[ReplyButton] | None = Field(
        None, description="Buttons to send to all users"
    )
    filters: BotBroadcastFilters | None = Field(
        None,
        description="Filters to select users to broadcast to. If not provided, will broadcast to all users of this bot.",
    )


R = typing.TypeVar("R", bound=BotBroadcastRequestModel)


@app.post(
    f"/v2/{VideoBotsPage.slug_versions[0]}/broadcast/send/",
    operation_id=VideoBotsPage.slug_versions[0] + "__broadcast",
    tags=["Misc"],
    name="Send Broadcast Message",
)
@app.post(
    f"/v2/{VideoBotsPage.slug_versions[0]}/broadcast/send",
    include_in_schema=False,
)
def broadcast_api_json(
    bot_request: BotBroadcastRequestModel,
    api_key: ApiKey = Depends(api_auth_header),
    example_id: str | None = None,
    run_id: str | None = None,
):
    bi_qs = BotIntegration.objects.filter(workspace=api_key.workspace)
    if example_id:
        bi_qs = bi_qs.filter(
            Q(published_run__published_run_id=example_id)
            | Q(saved_run__example_id=example_id)
        )
    elif run_id:
        bi_qs = bi_qs.filter(
            saved_run__run_id=run_id, saved_run__workspace=api_key.workspace
        )
    elif bot_request.integration_id:
        from routers.bots_api import api_hashids

        try:
            bi_id_decoded = api_hashids.decode(bot_request.integration_id)[0]
            bi_qs = bi_qs.filter(id=bi_id_decoded)
        except IndexError:
            return HTTPException(
                status_code=404,
                detail="Could not find a bot in your account with the given integration_id.",
            )
    else:
        return HTTPException(
            status_code=400,
            detail="Must provide one of the following: example_id or run_id as query parameters, or integration_id in the request body.",
        )
    if not bi_qs.exists():
        return HTTPException(
            status_code=404,
            detail=f"Could not find a bot in your account with the given {example_id=} & {run_id=} & {bot_request.integration_id=}. "
            "Please use the same account that you used to create the bot.",
        )

    total = 0
    for bi in bi_qs:
        convo_qs = bi.conversations.all()
        filters = bot_request.filters
        if filters:
            if filters.slack_user_id__in:
                # some input santization
                filters.slack_user_id__in = [
                    user_id.strip("<@>") for user_id in filters.slack_user_id__in
                ]
            convo_qs = convo_qs.filter(**filters.model_dump(exclude_unset=True))
            if bi.platform == Platform.SLACK:
                convo_qs = ensure_slack_personal_channels(
                    bi, filters, convo_qs
                ).distinct("slack_channel_id")
            else:
                convo_qs = convo_qs.distinct_by_user_id()

        if not convo_qs.exists():
            raise HTTPException(
                status_code=404,
                detail=f"No conversations found with the given filters: {filters.model_dump(exclude_unset=True)}",
            )

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


def ensure_slack_personal_channels(
    bi: BotIntegration,
    filters: BotBroadcastFilters,
    convo_qs: QuerySet[Conversation],
) -> QuerySet[Conversation]:
    # note: explicit False check here because None means both public and personal channels
    if filters.slack_channel_is_personal is False or not filters.slack_user_id__in:
        return convo_qs

    missing_user_ids = set(filters.slack_user_id__in) - set(
        convo_qs.values_list("slack_user_id", flat=True)
    )
    if not missing_user_ids:
        return convo_qs

    for user_id in missing_user_ids:
        user = fetch_user_info(user_id, bi.slack_access_token)
        create_personal_channel(bi, user)

    return convo_qs.filter(**filters.model_dump(exclude_unset=True))
