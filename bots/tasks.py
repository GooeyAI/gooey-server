import json
from json import JSONDecodeError

from celery import shared_task
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from loguru import logger

from app_users.models import AppUser
from bots.models import (
    Message,
    CHATML_ROLE_ASSISSTANT,
    BotIntegration,
    Conversation,
    Platform,
    SavedRun,
    BotIntegrationAnalysisRun,
)
from daras_ai_v2.facebook_bots import WhatsappBot
from daras_ai_v2.functional import flatten, map_parallel
from daras_ai_v2.language_model import get_entry_text
from daras_ai_v2.slack_bot import (
    fetch_channel_members,
    create_personal_channel,
    SlackBot,
)
from daras_ai_v2.vector_search import references_as_prompt
from gooeysite.bg_db_conn import get_celery_result_db_safe
from recipes.VideoBots import ReplyButton

MAX_PROMPT_LEN = 100_000


@shared_task
def create_personal_channels_for_all_members(bi_id: int):
    bi = BotIntegration.objects.get(id=bi_id)
    users = list(fetch_channel_members(bi.slack_channel_id, bi.slack_access_token))
    map_parallel(lambda user: create_personal_channel(bi, user), users, max_workers=10)


@shared_task(bind=True)
def msg_analysis(self, msg_id: int, anal_id: int, countdown: int | None):
    anal = BotIntegrationAnalysisRun.objects.get(id=anal_id)

    if (
        countdown
        and anal.scheduled_task_id
        and anal.scheduled_task_id != self.request.id
    ):
        logger.warning(
            f"Skipping analysis {anal} because another task is already scheduled"
        )
        return

    anal.last_run_at = timezone.now()
    anal.scheduled_task_id = None
    anal.save(update_fields=["last_run_at"])

    msg = Message.objects.get(id=msg_id)
    assert (
        msg.role == CHATML_ROLE_ASSISSTANT
    ), f"the message being analyzed must must be an {CHATML_ROLE_ASSISSTANT} msg"

    billing_account = AppUser.objects.get(
        uid=msg.conversation.bot_integration.billing_account_uid
    )
    analysis_sr = anal.get_active_saved_run()

    # add variables to the script
    variables = analysis_sr.state.get("variables", {}) | dict(
        user_msg=msg.get_previous_by_created_at().content,
        user_msg_local=msg.get_previous_by_created_at().display_content,
        assistant_msg=msg.content,
        assistant_msg_local=msg.display_content,
        bot_script=msg.saved_run and msg.saved_run.state.get("bot_script", ""),
        references=(
            msg.saved_run
            and references_as_prompt(msg.saved_run.state.get("references", []))
        ),
    )
    if msg.saved_run:
        for requested_variable in analysis_sr.state.get("variables", {}).keys():
            variables[requested_variable] = msg.saved_run.state.get(requested_variable)

    # these are resource intensive, so only include them if the script asks for them
    if "messages" in variables:
        variables["messages"] = "\n".join(
            f'{entry["role"]}: """{get_entry_text(entry)}"""'
            for entry in msg.conversation.msgs_as_llm_context()
        )

    if "conversations" in variables:
        conversations = []
        for convo in msg.conversation.bot_integration.conversations.order_by(
            "-created_at"
        ):
            if sum(map(len, conversations)) > MAX_PROMPT_LEN:
                break
            conversations.append(
                "\n".join(
                    f'{entry["role"]}: """{get_entry_text(entry)}"""'
                    for entry in convo.msgs_as_llm_context()
                )
            )
        variables["conversations"] = "\n####\n".join(conversations)

    # make the api call
    result, sr = analysis_sr.submit_api_call(
        current_user=billing_account, request_body=dict(variables=variables)
    )

    # save the run before the result is ready
    Message.objects.filter(id=msg_id).update(analysis_run=sr)

    # wait for the result
    get_celery_result_db_safe(result)
    sr.refresh_from_db()
    # if failed, raise error
    if sr.error_msg:
        raise RuntimeError(sr.error_msg)

    # save the result as json
    output_text = flatten(sr.state["output_text"].values())[0]
    try:
        analysis_result = json.loads(output_text)
    except JSONDecodeError:
        analysis_result = {
            "error": "Failed to parse the analysis result. Please check your script.",
        }
    with transaction.atomic():
        msg = Message.objects.get(id=msg_id)
        # merge the analysis result with the existing one
        msg.analysis_result = (msg.analysis_result or {}) | analysis_result
        # save the result
        msg._analysis_started = True  # prevent infinite recursion
        msg.save(update_fields=["analysis_result"])


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
                    access_token=bi.wa_business_access_token,
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
