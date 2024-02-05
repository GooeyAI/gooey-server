import json

from celery import shared_task
from django.db.models import QuerySet

from app_users.models import AppUser
from bots.models import (
    Message,
    CHATML_ROLE_ASSISSTANT,
    BotIntegration,
    Conversation,
    Platform,
)
from daras_ai_v2.facebook_bots import WhatsappBot
from daras_ai_v2.functional import flatten, map_parallel
from daras_ai_v2.slack_bot import (
    fetch_channel_members,
    create_personal_channel,
    SlackBot,
)
from daras_ai_v2.vector_search import references_as_prompt
from recipes.VideoBots import ReplyButton


@shared_task
def create_personal_channels_for_all_members(bi_id: int):
    bi = BotIntegration.objects.get(id=bi_id)
    users = list(fetch_channel_members(bi.slack_channel_id, bi.slack_access_token))
    map_parallel(lambda user: create_personal_channel(bi, user), users, max_workers=10)


@shared_task
def msg_analysis(msg_id: int):
    msg = Message.objects.get(id=msg_id)
    assert (
        msg.role == CHATML_ROLE_ASSISSTANT
    ), f"the message being analyzed must must be an {CHATML_ROLE_ASSISSTANT} msg"

    bi = msg.conversation.bot_integration
    analysis_sr = bi.analysis_run
    assert analysis_sr, "bot integration must have an analysis run"

    # make the api call
    billing_account = AppUser.objects.get(uid=bi.billing_account_uid)
    variables = dict(
        user_msg=msg.get_previous_by_created_at().content,
        assistant_msg=msg.content,
        bot_script=msg.saved_run.state.get("bot_script", ""),
        references=references_as_prompt(msg.saved_run.state.get("references", [])),
    )
    result, sr = analysis_sr.submit_api_call(
        current_user=billing_account,
        request_body=dict(variables=variables),
    )

    # save the run before the result is ready
    Message.objects.filter(id=msg_id).update(analysis_run=sr)

    # wait for the result
    result.get(disable_sync_subtasks=False)
    sr.refresh_from_db()
    # if failed, raise error
    if sr.error_msg:
        raise RuntimeError(sr.error_msg)

    # save the result as json
    Message.objects.filter(id=msg_id).update(
        analysis_result=json.loads(flatten(sr.state["output_text"].values())[0]),
    )


def send_broadcast_msgs_chunked(
    *,
    text: str,
    audio: str,
    video: str,
    documents: list[str],
    buttons: list[ReplyButton] = None,
    convo_qs: QuerySet[Conversation],
    bi: BotIntegration,
):
    convo_ids = list(convo_qs.values_list("id", flat=True))
    for i in range(0, len(convo_ids), 100):
        send_broadcast_msg.delay(
            text=text,
            audio=audio,
            video=video,
            buttons=buttons,
            documents=documents,
            bi_id=bi.id,
            convo_ids=convo_ids[i : i + 100],
        )


@shared_task
def send_broadcast_msg(
    *,
    text: str | None,
    audio: str = None,
    video: str = None,
    buttons: list[ReplyButton] = None,
    documents: list[str] = None,
    bi_id: int,
    convo_ids: list[int],
):
    bi = BotIntegration.objects.get(id=bi_id)
    convos = Conversation.objects.filter(id__in=convo_ids)
    for convo in convos:
        match bi.platform:
            case Platform.WHATSAPP:
                msg_id = WhatsappBot.send_msg_to(
                    text=text,
                    audio=audio,
                    video=video,
                    buttons=buttons,
                    documents=documents,
                    bot_number=bi.wa_phone_number_id,
                    user_number=convo.wa_phone_number.as_e164,
                )
            case Platform.SLACK:
                msg_id = SlackBot.send_msg_to(
                    text=text,
                    audio=audio,
                    video=video,
                    buttons=buttons,
                    documents=documents,
                    channel=convo.slack_channel_id,
                    channel_is_personal=convo.slack_channel_is_personal,
                    username=bi.name,
                    token=bi.slack_access_token,
                )[0]
            case _:
                raise NotImplementedError(
                    f"Platform {bi.platform} doesn't support broadcasts yet"
                )
        # save_broadcast_message(convo, text, msg_id)


## Disabled for now to prevent messing up the chat history
# def save_broadcast_message(convo: Conversation, text: str, msg_id: str | None = None):
#     message = Message(
#         conversation=convo,
#         role=CHATML_ROLE_ASSISTANT,
#         content=text,
#         display_content=text,
#         saved_run=None,
#     )
#     if msg_id:
#         message.platform_msg_id = msg_id
#     message.save()
#     return message
