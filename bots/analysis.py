from .models import Message
import requests
import json

GOOEY_API_KEY = "sk-zFzCpZ2zBUKNEkg0cayMphqg10p6QqfEQ85W2gNNdpd1glOU"
INPUT_PROMPT: str = ""


def msg_analysis(msg):
    global INPUT_PROMPT

    # Get the message ID
    message_id = msg.id

    # If statement to determine user or bot message
    if msg.role == "user":
        INPUT_PROMPT = "user: " + msg.content
    elif msg.role == "assistant":
        INPUT_PROMPT += "assistant: " + msg.content

        # Access the associated BotIntegration object
        BOT_INTEGRATION = msg.conversation.bot_integration

        # Access the analysis_url of the BotIntegration object
        ANALYSIS_URL = BOT_INTEGRATION.analysis_url

        payload = {"input_prompt": INPUT_PROMPT}

        response = requests.post(
            ANALYSIS_URL,
            headers={
                "Authorization": "Bearer " + GOOEY_API_KEY,
            },
            json=payload,
        )

        result = response.json()

        result_json = result.get("output").get("output_text")[0]

        # print(str(response.status_code) + "\n", result_json)
        print(result_json)
        result_dict = json.loads(result_json)

        question_answered(result_dict, message_id)
        question_subject(result_dict, message_id)


def question_answered(
    dict,
    id,
):
    q_answered = Message.objects.get(id=id)
    q_answered.question_answered = dict["assistant"]["answer"]
    q_answered.save()


def question_subject(
    dict,
    id,
):
    q_subject = Message.objects.get(id=id)
    q_subject.question_subject = dict["user"]["subject"]
    q_subject.save()
