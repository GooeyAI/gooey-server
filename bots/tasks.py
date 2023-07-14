import json

import jinja2

from celery import shared_task
from daras_ai_v2.language_model import run_language_model, LargeLanguageModels
from bots.models import Message, CHATML_ROLE_ASSISSTANT

ANALYSIS_PROMPT = '''\
Your job is to analyze incoming chat messages from farmers and the responses from a farming ai chatbot and determine how to categorize them.

For the assistant answer, only tell if the answer is "found" or "missing".

The answer is only missing if the assistant:
---
1. Can not give any additional information
2. Apologizes
3. Tells the user to check a website
---
If it does not say all three things, the answer has been found.

For the user's subject answer, choose from the following list as category:

Subject Answers
*********************
(A): Salutation
(B): Plant Death (Infestation and Infection)
(C): Farming Practice
(D): Irrigation
(E): Video
(G): Supplements (Fertilizers and Pesticides)
(H): Unknown Category
*********************
Assistant Answers
*********************
(Y): Found
(N): Missing
*********************

If the input messages are salutations, ignore the previous format and instructions and return the following message verbatim: {"message": “A”}

Conversation: """
   user: Hi
   assistant: Hello! How can I assist you with farming today?
"""
Analysis: {"message": “A”}
///
Conversation: """
   user: My rice crop has yellow stem borer infestation. Please suggest
   assistant: Yellow stem borer is a major pest of rice crops. Here are some management practices that can help control the infestation of yellow stem borer in rice crops:

1. Use resistant varieties of rice such as Ratna, Sasyasree, Vikas, HKR 46, NDGR 21, Pantdhan 6, VLK 39, Prahlad, Birsadhan 201, Bhudeb Ainesh, Matangini, Radha, Sudha, Amulya, Bhagirathi, Jogan, Mandira, Nalini, Sabita, VL16 and VL 206. [2][3]

2. Cultural practices such as seed treatment with approved biopesticides or chemical pesticides before sowing, removing and destroying the grass weed hosts in the field bunds, channel or nearby areas of rice fields as these serve as alternative hosts for the pest, avoiding close spacing as it often increases the easy movement of pest, handpicking and destroying egg masses in the seedbed (nursery) before transplanting the field, cutting the leaf-top before transplanting to reduce carry-over of eggs from the seedbed to the field, raising the level of irrigation water periodically to submerge any eggs deposited on the lower parts of the plant, cutting out the stems with dead hearts and removing them from the field and destroying the larvae or burning the stem, and splitting applications of nitrogen fertilizer. High nitrogen application favors build-up of stem
"""
Analysis: {"user": {"crop":”rice”, "subject":”B”, "location":null}, "assistant": {"answer":”Y”}}
///
Conversation: """
   user: A drug can be used to increase the height of chillies in the chilli garden
   assistant: I'm sorry, but I couldn't find any information in the search results about a drug that can increase the height of chillies in a garden. It is important to note that using untested or unverified drugs on crops can be harmful and may not be effective. It is best to consult with a local agriculture expert for specific recommendations for your district and type of plant.
"""
Analysis: {"user": {"crop":”chili”, "subject":”G”, "location":null}, "assistant": {"answer":”N”}}
///
Conversation: """
   user: Tell me about organic farming
   assistant: Organic farming is a method of farming that avoids the use of synthetic fertilizers, pesticides, and genetically modified organisms (GMOs). Instead, it relies on natural methods like crop rotation, composting, and biological pest control to maintain soil fertility and control pests. Organic farming also emphasizes the use of renewable resources and conservation of water and soil. [1]
"""
Analysis: {"user": {"crop": null, "subject": "C", "location": null}, "assistant": {"answer": "Y"}}
///
Conversation: """
   user: How many days should be watered after making the pepper garden?
   assistant: According to [1], immediately after transplanting chilli seedlings to the field, the field should be irrigated. The second irrigation is given 10 days after transplanting. Afterward, irrigation is given as per the requirement. Generally, 8 to 9 irrigations are given depending on rainfall, soil type, humidity, and temperature. The method of irrigation adopted is ridges and furrow. For more specific information on irrigation practices for your particular crop and district, please consult with your local agriculture extension office or watch relevant videos on https://www.digitalgreen.org/videos. 💦
"""
Analysis: {"user": {"crop":"pepper", "subject":"D", "location":null}, "assistant": {"answer":"Y"}}
///
Conversation: """
   user: Reasons why chillies fall apart
   assistant: Chillies can fall apart due to several reasons, including environmental conditions, pests, and diseases. Inadequate pollination due to low bee activity or high temperatures can lead to poor fruit development and cause the chillies to fall apart [2]. Nutrient deficiencies, particularly a lack of phosphorus, can also affect fruit development and cause the chillies to fall apart [1]. Additionally, pests such as the chilli blossom midge can cause poor development of fruits, leading to the chillies falling apart [3]. It is important to consult with a local agriculture expert to identify the specific cause and recommend appropriate management practices for your district and type of plant. For more information on farming in India, you can visit https://www.digitalgreen.org/videos. 🌶️🌱
"""
Analysis: {"user": {"crop":”chili”, "subject":”B”, "location":null}, "assistant": {"answer":”Y”}}
///
Conversation: """
   user: How to prepare dukki for planting chili garden
   assistant: I'm sorry, I couldn't find any relevant information on preparing "dukki" for planting chili garden in the search results. Could you please provide more context or try rephrasing your question?
"""
Analysis: {"user": {"crop":"chili", "subject":"C", "location": null}, "assistant": {"answer":"N"}}
///
Conversation: """
   user: Is there a video for this?
   assistant: I'm sorry, I don't have enough information to answer your question. However, you can visit https://www.digitalgreen.org/videos to find helpful videos on various farming practices in India.
"""
Analysis: {"user": {"crop": null, "subject":"E", "location": null, "assistant": {"answer":"N"}}
///
Conversation: """
   user: Which crop can be planted in Anantapur?
   assistant: Anantapur district in Andhra Pradesh is suitable for growing crops like groundnut, maize, jowar, sunflower, cotton, and chilli. However, the choice of crop depends on various factors such as soil type, climate, and water availability. It is recommended to consult with local agricultural experts or extension officers to determine the best crop for a particular area. [1]
"""
Analysis: {"user": {"crop": null, "subject":"C", "location":"Anantapur"'}, "assistant": {"answer":"Y"}}
///
Conversation: """
   user: {{ user_msg }}
   assistant:  {{ assistant_msg }}
"""
Analysis:'''

QUESTION_SUBJECTS = {
    "A": "Salutation",
    "B": "Plant Death (Infestation and Infection)",
    "C": "Farming Practice",
    "D": "Irrigation",
    "E": "Video",
    "G": "Supplements (Fertilizers and Pesticides)",
    "H": "Unknown Category",
}
QUESTION_ANSWERED_CHOICES = {
    "Y": "Found",
    "N": "Missing",
}


@shared_task
def msg_analysis(msg_id: int):
    msg = Message.objects.get(id=msg_id)
    assert (
        msg.role == CHATML_ROLE_ASSISSTANT
    ), f"the message being analyzed must must be an {CHATML_ROLE_ASSISSTANT} msg"

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
    try:
        msg.question_subject = QUESTION_SUBJECTS[result_dict["user"]["subject"]]
    except KeyError:
        pass
    try:
        msg.question_answered = QUESTION_ANSWERED_CHOICES[
            result_dict["assistant"]["answer"]
        ]
    except KeyError:
        pass
    msg._analysis_done = True
    msg.save()
