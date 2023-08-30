from enum import Enum

import gooey_ui as st
from google.cloud import texttospeech

from daras_ai_v2.enum_selector_widget import enum_selector

UBERDUCK_VOICES = {

    "Aiden Botha": "b01cf18d-0f10-46dd-adc6-562b599fdae4",
    "Angus": "7d29a280-8a3e-4c4b-9df4-cbe77e8f4a63",
    "Damon Edwards Deep": "df71a60f-1294-4cf1-bd5d-a7e6d7350178",
    "General Herring":"818bc1dd-1d34-4205-81a8-5e32dfec3e2b",
    "Zeus":"92022a27-75fb-4e15-90ca-95095a82f5ee",
    "Rose":"e76808ae-e81d-46a1-97cd-29bc3783d25b",
    "Davo":"23fb3c48-4115-4525-84c8-90dba2c290d6",
    "Kiwi":"769bdb7a-2763-4e2a-a4e5-d237727e033e",
    "Bertie":"080e856b-6fcd-4010-bd3a-3bc0712037a3",
    "Jake Turner":"13c0b24a-abff-4c30-9729-7250844ef314",
    "Carolyn Samuelson":"60c910d0-d924-4f74-a47c-6c9e44e2bb8b"
}


class TextToSpeechProviders(Enum):
    GOOGLE_TTS = "Google Cloud Text-to-Speech"
    UBERDUCK = "uberduck.ai"
    BARK = "Bark (suno-ai)"


BARK_SUPPORTED_LANGS = [
    ("English", "en"),
    ("German", "de"),
    ("Spanish", "es"),
    ("French", "fr"),
    ("Hindi", "hi"),
    ("Italian", "it"),
    ("Japanese", "ja"),
    ("Korean", "ko"),
    ("Polish", "pl"),
    ("Portuguese", "pt"),
    ("Russian", "ru"),
    ("Turkish", "tr"),
    ("Chinese", "zh"),
]

BARK_ALLOWED_PROMPTS = {
    None: "———",
    "announcer": "Announcer",
} | {
    f"{code}_speaker_{n}": f"Speaker {n} ({lang})"
    for lang, code in BARK_SUPPORTED_LANGS
    for n in range(10)
}


def text_to_speech_settings():
    st.write(
        """
        ##### 🗣️ Voice Settings
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
        case TextToSpeechProviders.BARK.name:
            with col2:
                st.selectbox(
                    label="""
                    ###### Bark History Prompt
                    """,
                    key="bark_history_prompt",
                    format_func=BARK_ALLOWED_PROMPTS.__getitem__,
                    options=BARK_ALLOWED_PROMPTS.keys(),
                )

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
                    format_func=lambda option: f"{option}",
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


@st.cache_data()
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
