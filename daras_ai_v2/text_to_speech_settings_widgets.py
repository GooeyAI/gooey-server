from enum import Enum

import streamlit as st
from google.cloud import texttospeech

from daras_ai_v2.enum_selector_widget import enum_selector

UBERDUCK_VOICES = {
    "hecko": "Reserved Male European",
    "ryan-gosling": "Laidback US Male",
    "elsa": "Earnest Female US",
    "judi-dench": "Older Female UK 70s",
    "rc-bray": "Wise Male US 50s",
    "dr-phil": "Southern Drawl US Male",
    "3kliksphilip": "Upbeat Male UK",
    "ellen": "Mellow Female US",
    "steve-irwin": "Casual Male Australian",
    "pam-beesly": "Soft-spoken Female US",
    "mark-elliott": "Friendly Older Male US",
    "woody-jh": "Cheery Southern Male US",
    "judy-hopps": "Upbeat Female US",
    "the-rock": "Samoan Action Star",
}


class TextToSpeechProviders(Enum):
    GOOGLE_TTS = "Google Cloud Text-to-Speech"
    UBERDUCK = "uberduck.ai"


def text_to_speech_settings():
    st.write(
        """
        #### 🗣️ Voice Settings
        """
    )

    col1, col2 = st.columns(2)
    with col1:
        tts_provider = enum_selector(
            TextToSpeechProviders,
            "###### Speech Provider",
            key="tts_provider",
        )

    match tts_provider:
        case TextToSpeechProviders.GOOGLE_TTS.name:
            with col2:
                voices = google_tts_voices()
                st.selectbox(
                    label="""
                    ###### Voice name (Google TTS)
                    """,
                    key="google_voice_name",
                    format_func=voices.__getitem__,
                    options=voices.keys(),
                )
                st.caption(
                    "*Please refer to the list of voice names [here](https://cloud.google.com/text-to-speech/docs/voices)*"
                )

            col1, col2 = st.columns(2)
            with col1:
                st.slider(
                    """
                    ###### Speaking rate 
                    *`1.0` is the normal native speed of the speaker*
                    """,
                    min_value=0.3,
                    max_value=4.0,
                    step=0.1,
                    key="google_speaking_rate",
                )
            with col2:
                st.slider(
                    """
                    ###### Pitch
                    *Increase/Decrease semitones from the original pitch*
                    """,
                    min_value=-20.0,
                    max_value=20.0,
                    step=0.25,
                    key="google_pitch",
                )

        case TextToSpeechProviders.UBERDUCK.name:
            with col2:
                st.selectbox(
                    label="""
                    ###### Voice name (Uberduck)
                    """,
                    key="uberduck_voice_name",
                    format_func=lambda option: f"{UBERDUCK_VOICES[option]} | {option}",
                    options=UBERDUCK_VOICES.keys(),
                )

            col1, col2 = st.columns(2)
            with col1:
                st.slider(
                    """
                    ###### Speaking rate 
                    *`1.0` is the normal native speed of the speaker*
                    """,
                    min_value=0.5,
                    max_value=3.0,
                    step=0.25,
                    key="uberduck_speaking_rate",
                )


@st.cache
def google_tts_voices() -> dict[texttospeech.Voice, str]:
    voices: list[texttospeech.Voice] = (
        texttospeech.TextToSpeechClient().list_voices().voices
    )
    voices.sort(key=_voice_sort_key)
    return {voice.name: _pretty_voice(voice) for voice in voices}


def _pretty_voice(voice) -> str:
    return f"{voice.name} ({voice.ssml_gender.name.capitalize()})"


_lang_code_sort = ["en-US", "en-IN", "en-GB", "en-AU"]


def _voice_sort_key(voice: texttospeech.Voice):
    try:
        lang_index = _lang_code_sort.index(voice.language_codes[0])
    except ValueError:
        lang_index = len(_lang_code_sort)
    return (
        # sort by lang code
        lang_index,
        # put wavenet first
        1 - ("Wavenet" in voice.name),
        # sort alphabetically
        voice.name,
    )
