import json
import time

import gooey_gui as gui
import requests
from decouple import config


def get_audio(uuid):
    with gui.spinner(f"Generating your audio file ..."):
        while True:
            data = requests.get(f"https://api.uberduck.ai/speak-status?uuid={uuid}")
            path = json.loads(data.text)["path"]
            if path:
                gui.audio(path)
                break
            else:
                time.sleep(2)


def main():
    gui.write("# Text To Audio")

    with gui.form(key="send_email", clear_on_submit=False):
        voice = gui.text_input(label="Voice", value="zwf")
        text = gui.text_area(label="Text input", value="This is a test.")
        submitted = gui.form_submit_button("Generate")
        if submitted:
            response = requests.post(
                "https://api.uberduck.ai/speak",
                auth=(config("UBERDUCK_KEY"), config("UBERDUCK_SECRET")),
                json={"speech": text, "voice": voice},
            )
            uuid = json.loads(response.text)["uuid"]
            get_audio(uuid)
            # send_email()


main()
