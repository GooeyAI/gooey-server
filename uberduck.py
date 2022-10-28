import json
import smtplib
import time
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from os.path import basename

import requests
import streamlit as st
from decouple import config


def get_audio(uuid):
    with st.spinner(f'Generating your audio file ...'):
        while True:
            data = requests.get(f"https://api.uberduck.ai/speak-status?uuid={uuid}")
            path = json.loads(data.text)["path"]
            if path:
                st.audio(path)
                break
            else:
                time.sleep(2)


def main():
    st.write("# Text To Audio")

    with st.form(key="send_email", clear_on_submit=False):
        voice = st.text_input(label="Voice", value="zwf")
        text = st.text_area(label="Text input", value="This is a test.")
        submitted = st.form_submit_button("Generate")
        if submitted:
            response = requests.post(
                "https://api.uberduck.ai/speak",
                auth=(config("UBERDUCK_KEY"), config("UBERDUCK_SECRET")),
                json={"speech": text, "voice": voice}
            )
            uuid = json.loads(response.text)["uuid"]
            get_audio(uuid)
            # send_email()


main()
