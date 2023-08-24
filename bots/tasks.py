import json

import jinja2

from celery import shared_task
from daras_ai_v2.language_model import run_language_model, LargeLanguageModels
from bots.models import Message, CHATML_ROLE_ASSISSTANT


@shared_task
def msg_analysis(msg_id: int):
    msg = Message.objects.get(id=msg_id)
    ANALYSIS_PROMPT= msg.conversation.bot_integration.analysis_run.state['input_prompt']
    assert (
        msg.role == CHATML_ROLE_ASSISSTANT
    ), f"the message being analyzed must be an {CHATML_ROLE_ASSISSTANT} msg"

    prompt = jinja2.Template(ANALYSIS_PROMPT).render(
        user_msg=msg.get_previous_by_created_at().content,
        assistant_msg=msg.content,
    )

    response = run_language_model(
        model=LargeLanguageModels.gpt_3_5_turbo_16k.name,
        messages=[
            {"role": "system", "content": "You are an intelligent and expert analyst"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=256,
        temperature=0.2,
    )[0]

    result_dict = json.loads(response)

    msg.refresh_from_db()
    msg.analysis_data = result_dict
    try:
        msg.question_subject = result_dict["user"]["subject"]
    except KeyError:
        pass
    try:
        msg.question_answered = result_dict["assistant"]["answer"]
        
    except KeyError:
        pass
    msg._analysis_done = True
    msg.save()
