import os
import uuid
from threading import Thread

import gooey_gui as gui
import openai
from fastapi import FastAPI

app = FastAPI()


@gui.route(app, "/poem/")
def root():
    gui.write("### Poem Generator")
    prompt = gui.text_input(
        "What kind of poem do you want to generate?", value="john lennon"
    )
    if gui.button("Generate 🪄"):
        # a unique channel name for redis pubsub
        gui.session_state["channel"] = channel = f"poem-generator/{uuid.uuid4()}"
        # start the thread
        Thread(target=generate_poem_thread, args=[prompt, channel]).start()

    channel = gui.session_state.get("channel")
    if not channel:
        # no channel, no need to subscribe
        return

    # fetch updates from redis pubsub
    result = gui.realtime_pull([channel])[0]
    if result is None:
        # no result yet
        gui.write("Running Thread...")
        return

    # display result / loading message
    gui.write(result)

    ## optionally, stop subscribing from the channel and store result in session state
    # gui.session_state.pop("channel")
    # gui.session_state["poem"] = result


def generate_poem_thread(prompt, channel):
    openai.api_key = os.getenv("OPENAI_API_KEY")

    completion = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a brilliant poem writer."},
            {"role": "user", "content": prompt},
        ],
    )
    result = completion.choices[0].message.content or ""

    # push the result to the channel + reload the UI
    gui.realtime_push(channel, result)
