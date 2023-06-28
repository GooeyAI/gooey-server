from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Message
import os
import requests
from .tasks import save_JSON_to_queue, confirm_message_answered_content
import json


GOOEY_API_KEY = "sk-zFzCpZ2zBUKNEkg0cayMphqg10p6QqfEQ85W2gNNdpd1glOU"
INPUT_PROMPT: str = ""


# Receiver for Message Signal
@receiver(post_save, sender=Message)
def run_after_message_save(sender, instance, created, **kwargs):
    global INPUT_PROMPT
    if created:
        message_id = instance.id  # Get the message ID
        print("instance.content: " + instance.content)

        # if statement to determine user or bot message
        if instance.role == "user":
            INPUT_PROMPT = "user: " + instance.content
        elif instance.role == "assistant":
            INPUT_PROMPT += "\nassistant: " + instance.content

            payload = {"input_prompt": INPUT_PROMPT}

            response = requests.post(
                "https://api.gooey.ai/v2/video-bots/?run_id=uflky8xk&uid=vkbEEF3tEHSTIVvvirBYDS9jP5w2",
                headers={
                    "Authorization": "Bearer " + GOOEY_API_KEY,
                },
                json=payload,
            )

            # https://api.gooey.ai/v2/video-bots/?example_id=5jm4z523
            result = response.json()

            result_json = result.get("output").get("output_text")[0]

            # save_JSON_to_queue.delay(result.get("output").get("output_text")[0], message_id)
            # confirm_message_answered_content.delay(message_id)
            # handle_message(result)

            print(str(response.status_code) + "\n", result_json)
            result_dict = json.loads(result_json)
            print(result_dict["assistant"]["answer"])

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
