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
    change_voice = st.button("Change voice")
    voices = ('zwf',)
    if change_voice:
        voices_resp = requests.get("https://api.uberduck.ai/voices?mode=tts-basic&language=english",
                                   auth=(config("UBERDUCK_KEY"), config("UBERDUCK_SECRET")),
                                   )
        if voices_resp.status_code == 200:
            data = json.loads(voices_resp.text)
            st.write(data)

        option = st.selectbox(
            'Change voice',
            ('zwf', 'Home phone', 'Mobile phone'))
        st.write('You selected:', option)
        st.write(voices)

    with st.form(key="send_email", clear_on_submit=False):
        text = st.text_area(label="Text input", value="This is a test.")
        submitted = st.form_submit_button("Send")
        if submitted:
            response = requests.post(
                "https://api.uberduck.ai/speak",
                auth=(config("UBERDUCK_KEY"), config("UBERDUCK_SECRET")),
                json={"speech": text, "voice": "zwf"}
            )
            uuid = json.loads(response.text)["uuid"]
            get_audio(uuid)
            # send_email()


main()
