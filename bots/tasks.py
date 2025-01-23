import json
from datetime import timedelta
from json import JSONDecodeError

import sentry_sdk
from celery import shared_task
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from loguru import logger

from bots.models import (
    BotIntegrationScheduledFunction,
    Message,
    CHATML_ROLE_ASSISSTANT,
    BotIntegration,
    Conversation,
    Platform,
    BotIntegrationAnalysisRun,
)
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.facebook_bots import WhatsappBot
from daras_ai_v2.functional import flatten, map_parallel
from daras_ai_v2.slack_bot import (
    fetch_channel_members,
    create_personal_channel,
    SlackBot,
)
from daras_ai_v2.twilio_bot import send_single_voice_call, send_sms_message
from daras_ai_v2.vector_search import references_as_prompt
from recipes.VideoBots import ReplyButton, messages_as_prompt
from recipes.VideoBotsStats import get_conversations_and_messages, get_tabular_data

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

    analysis_sr = anal.get_active_saved_run()
    variables = analysis_sr.state.get("variables", {})

    if msg.saved_run:
        # add the variables from the parent run
        variables |= msg.saved_run.state.get("variables") or {}
        # add the state variables requested by the script
        fill_req_vars_from_state(msg.saved_run.state, variables)
    if "messages" in variables:
        variables["messages"] = messages_as_prompt(
            msg.conversation.msgs_for_llm_context()
        )
    if "conversations" in variables:
        variables["conversations"] = conversations_as_prompt(msg)

    # these vars always show up on the UI
    variables |= dict(
        user_msg=msg.get_previous_by_created_at().content,
        user_msg_local=msg.get_previous_by_created_at().display_content,
        assistant_msg=msg.content,
        assistant_msg_local=msg.display_content,
    )

    # make the api call
    result, sr = analysis_sr.submit_api_call(
        workspace=msg.conversation.bot_integration.workspace,
        current_user=msg.conversation.bot_integration.created_by,
        request_body=dict(variables=variables),
        parent_pr=anal.published_run,
    )

    # save the run before the result is ready
    Message.objects.filter(id=msg_id).update(analysis_run=sr)

    sr.wait_for_celery_result(result)
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


def conversations_as_prompt(msg: Message) -> str:
    ret = ""
    for convo in msg.conversation.bot_integration.conversations.order_by("-created_at"):
        if len(ret) > MAX_PROMPT_LEN:
            break
        ret += messages_as_prompt(convo.msgs_for_llm_context()) + "\n####\n"
    return ret.strip()


def fill_req_vars_from_state(state: dict, req_vars: dict):
    for key in req_vars.keys():
        try:
            value = state[key]
        except KeyError:
            continue
        if key == "references":
            value = references_as_prompt(value)
        req_vars[key] = value


def send_broadcast_msgs_chunked(
    *,
    text: str,
    audio: str,
    video: str,
    documents: list[str],
    buttons: list[ReplyButton] = None,
    convo_qs: QuerySet[Conversation],
    bi: BotIntegration,
    medium: str = "Voice Call",
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
            medium=medium,
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
    medium: str = "Voice Call",
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
            case Platform.TWILIO:
                if medium == "Voice Call":
                    send_single_voice_call(convo, text, audio)
                else:
                    send_sms_message(convo, text, media_url=audio)
            case _:
                raise NotImplementedError(
                    f"Platform {bi.platform} doesn't support broadcasts yet"
                )
        # save_broadcast_message(convo, text, msg_id)


@shared_task
def run_all_scheduled_functions():
    for sf in BotIntegrationScheduledFunction.objects.select_related(
        "bot_integration"
    ).exclude(last_run_at__gt=timezone.now() - timedelta(hours=23)):
        bi = sf.bot_integration
        today = timezone.now().date()
        conversations, messages = get_conversations_and_messages(bi)
        df = get_tabular_data(
            bi=sf.bot_integration,
            conversations=conversations,
            messages=messages,
            details="Messages",
            sort_by=None,
            start_date=today,
            end_date=today,
        )
        csv = df.to_csv()
        csv_url = upload_file_from_bytes(
            filename=f"stats-{today.strftime('%Y-%m-%d')}.csv",
            data=csv,
            content_type="text/csv",
        )

        fn_sr, fn_pr = sf.get_runs()
        result, fn_sr = fn_sr.submit_api_call(
            workspace=bi.workspace,
            request_body=dict(variables={"message_history_csv_url": csv_url}),
            parent_pr=fn_pr,
            current_user=bi.workspace.created_by,
        )
        sf.last_run_at = fn_sr.created_at
        sf.save(update_fields=["last_run_at"])
        fn_sr.wait_for_celery_result(result)

        if fn_sr.error_msg:
            # if failed, log error_msg
            logger.warning(f"errored... {fn_sr.error_msg}")
            sentry_sdk.capture_exception(RuntimeError(fn_sr.error_msg))
        else:
            logger.info(f"completed... {fn_sr.get_app_url()}")


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
