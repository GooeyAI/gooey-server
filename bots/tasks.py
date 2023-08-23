import json

from celery import shared_task

from app_users.models import AppUser
from bots.models import Message, CHATML_ROLE_ASSISSTANT
from daras_ai_v2.functional import flatten
from daras_ai_v2.vector_search import references_as_prompt


@shared_task
def msg_analysis(msg_id: int):
    msg = Message.objects.get(id=msg_id)
    assert (
        msg.role == CHATML_ROLE_ASSISSTANT
    ), f"the message being analyzed must must be an {CHATML_ROLE_ASSISSTANT} msg"

    bi = msg.conversation.bot_integration
    analysis_sr = bi.analysis_run
    assert analysis_sr, "bot integration must have an analysis run"

    variables = dict(
        user_msg=msg.get_previous_by_created_at().content,
        assistant_msg=msg.content,
        bot_script=msg.saved_run.state.get("bot_script", ""),
        references=references_as_prompt(msg.saved_run.state.get("references", [])),
    )
    billing_account = AppUser.objects.get(uid=bi.billing_account_uid)

    # make the api call
    page, result, run_id, uid = analysis_sr.submit_api_call(
        billing_account, variables=variables
    )
    result.get(disable_sync_subtasks=False)
    # get result
    sr = page.run_doc_sr(run_id, uid)
    # if failed, raise error
    if sr.error_msg:
        raise RuntimeError(sr.error_msg)

    Message.objects.filter(id=msg_id).update(
        analysis_run=sr,
        analysis_result=json.loads(flatten(sr.state["output_text"].values())[0]),
    )
