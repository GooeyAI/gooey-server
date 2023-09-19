import json

from celery import shared_task

from app_users.models import AppUser
from bots.models import Message, CHATML_ROLE_ASSISSTANT, BotIntegration
from daras_ai_v2.functional import flatten, map_parallel
from daras_ai_v2.slack_bot import fetch_channel_members, create_personal_channel
from daras_ai_v2.vector_search import references_as_prompt


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
