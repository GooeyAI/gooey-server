import uuid
import streamlit2 as st
from google.cloud import texttospeech
from enum import Enum

from daras_ai.image_input import upload_file_from_bytes
from google.oauth2 import service_account

credentials = service_account.Credentials.from_service_account_file(
    "serviceAccountKey.json"
)


class VoiceGender(Enum):
    FEMALE = 1
    MALE = 2
    NEUTRAL = 3


gender_dict = {
    VoiceGender.FEMALE.name: texttospeech.SsmlVoiceGender.FEMALE,
    VoiceGender.MALE.name: texttospeech.SsmlVoiceGender.MALE,
    VoiceGender.NEUTRAL.name: texttospeech.SsmlVoiceGender.NEUTRAL,
}


def main():
    st.write("# GOOGLE Text To Speach")

    with st.form(key="send_email", clear_on_submit=False):
        voice_name = st.text_input(label="Voice name", value="en-US-Neural2-F")
        st.write(
            "Get more voice names [here](https://cloud.google.com/text-to-speech/docs/voices)"
        )
        text = st.text_area(label="Text input", value="This is a test.")
        pitch = st.slider("Pitch", min_value=-20.0, max_value=20.0, value=0.0)
        speaking_rate = st.slider(
            "Speaking rate (1.0 is the normal native speed)",
            min_value=0.25,
            max_value=4.0,
            value=1.0,
        )
        # voice_gender = st.selectbox("Voice", (voice.name for voice in VoiceGender))
        submitted = st.form_submit_button("Generate")
        if submitted:
            client = texttospeech.TextToSpeechClient(credentials=credentials)

            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams()
            voice.language_code = "en-US"
            voice.name = voice_name  # optional

            # Select the type of audio file you want returned
            audio_config = texttospeech.AudioConfig()
            audio_config.audio_encoding = texttospeech.AudioEncoding.MP3
            audio_config.pitch = pitch  # optional
            audio_config.speaking_rate = speaking_rate  # optional

            # Perform the text-to-speech request on the text input with the selected
            # voice parameters and audio file type
            with st.spinner("Generating audio..."):
                response = client.synthesize_speech(
                    input=synthesis_input, voice=voice, audio_config=audio_config
                )
            if not response:
                st.error("Error: Audio generation failed")
                return

            with st.spinner("Uploading file..."):
                audio_url = upload_file_from_bytes(
                    f"google_tts_{uuid.uuid4()}.mp3", response.audio_content
                )

            if not audio_url:
                st.error("Error: Uploading failed")
                return
            st.audio(audio_url)


main()
