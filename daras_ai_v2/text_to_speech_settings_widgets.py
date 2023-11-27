from enum import Enum

import requests
from google.cloud import texttospeech

import gooey_ui as st
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.redis_cache import redis_cache_decorator

SESSION_ELEVENLABS_API_KEY = "__user__elevenlabs_api_key"

UBERDUCK_VOICES = {
    "Aiden Botha": "b01cf18d-0f10-46dd-adc6-562b599fdae4",
    "Angus": "7d29a280-8a3e-4c4b-9df4-cbe77e8f4a63",
    "Damon Edwards Deep": "df71a60f-1294-4cf1-bd5d-a7e6d7350178",
    "General Herring": "818bc1dd-1d34-4205-81a8-5e32dfec3e2b",
    "Zeus": "92022a27-75fb-4e15-90ca-95095a82f5ee",
    "Rose": "e76808ae-e81d-46a1-97cd-29bc3783d25b",
    "Davo": "23fb3c48-4115-4525-84c8-90dba2c290d6",
    "Kiwi": "769bdb7a-2763-4e2a-a4e5-d237727e033e",
    "Bertie": "080e856b-6fcd-4010-bd3a-3bc0712037a3",
    "Jake Turner": "13c0b24a-abff-4c30-9729-7250844ef314",
    "Carolyn Samuelson": "60c910d0-d924-4f74-a47c-6c9e44e2bb8b",
}


class TextToSpeechProviders(Enum):
    GOOGLE_TTS = "Google Cloud Text-to-Speech"
    ELEVEN_LABS = "Eleven Labs"
    UBERDUCK = "uberduck.ai"
    BARK = "Bark (suno-ai)"


# Mapping from Eleven Labs Voice Name -> Voice ID
ELEVEN_LABS_VOICES = {
    "Rachel": "21m00Tcm4TlvDq8ikWAM",
    "Clyde": "2EiwWnXFnvU5JabPnv8n",
    "Domi": "AZnzlk1XvdvUeBnXmlld",
    "Dave": "CYw3kZ02Hs0563khs1Fj",
    "Fin": "D38z5RcWu1voky8WS1ja",
    "Bella": "EXAVITQu4vr4xnSDxMaL",
    "Antoni": "ErXwobaYiN019PkySvjV",
    "Thomas": "GBv7mTt0atIp3Br8iCZE",
    "Charlie": "IKne3meq5aSn9XLyUdCD",
    "Emily": "LcfcDJNUP1GQjkzn1xUU",
    "Elli": "MF3mGyEYCl7XYWbV9V6O",
    "Callum": "N2lVS1w4EtoT3dr4eOWO",
    "Patrick": "ODq5zmih8GrVes37Dizd",
    "Harry": "SOYHLrjzK2X1ezoPC6cr",
    "Liam": "TX3LPaxmHKxFdv7VOQHJ",
    "Dorothy": "ThT5KcBeYPX3keUQqHPh",
    "Josh": "TxGEqnHWrfWFTfGW9XjX",
    "Arnold": "VR6AewLTigWG4xSOukaG",
    "Charlotte": "XB0fDUnXU5powFXDhCwa",
    "Matilda": "XrExE9yKIg1WjnnlVkGX",
    "Matthew": "Yko7PKHZNXotIFUBG7I9",
    "James": "ZQe5CZNOzWyzPSCn5a3c",
    "Joseph": "Zlb1dXrM653N07WRdFW3",
    "Jeremy": "bVMeCyTHy58xNoL34h3p",
    "Michael": "flq6f7yk4E4fJM5XTYuZ",
    "Ethan": "g5CIjZEefAph4nQFvHAz",
    "Gigi": "jBpfuIE2acCO8z3wKNLl",
    "Freya": "jsCqWAovK2LkecY7zXl4",
    "Grace": "oWAxZDx7w5VEj9dCyTzz",
    "Daniel": "onwK4e9ZLuTAKqWW03F9",
    "Serena": "pMsXgVXv3BLzUgSXRplE",
    "Adam": "pNInz6obpgDQGcFmaJgB",
    "Nicole": "piTKgcLEGmPE4e6mEKli",
    "Jessie": "t0jbNlBVZ17f02VDIeMI",
    "Ryan": "wViXBPUzp2ZZixB1xQuM",
    "Sam": "yoZ06aMxZJJ28mfd3POQ",
    "Glinda": "z9fAnlkpzviPz146aGWa",
    "Giovanni": "zcAOhNBS3c14rBihAFp1",
    "Mimi": "zrHiDhphv9ZnVXBqCLjz",
}

# Mapping from Model ID -> Title in UI
ELEVEN_LABS_MODELS = {
    "eleven_multilingual_v2": "Multilingual V2 - High quality speech in 29 languages",
    "eleven_turbo_v2": "English V2 - Very low latency text-to-speech",
    "eleven_monolingual_v1": "English V1 - Low latency text-to-speech",
}

ELEVEN_LABS_SUPPORTED_LANGS = [
    "English",
    "Japanese",
    "Chinese",
    "German",
    "Hindi",
    "French",
    "Korean",
    "Portuguese",
    "Italian",
    "Spanish",
    "Indonesian",
    "Dutch",
    "Turkish",
    "Filipino",
    "Polish",
    "Swedish",
    "Bulgarian",
    "Romanian",
    "Arabic",
    "Czech",
    "Greek",
    "Finnish",
    "Croatian",
    "Malay",
    "Slovak",
    "Danish",
    "Tamil",
    "Ukrainian",
    "Russian",
]

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


def text_to_speech_settings(page):
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

        case TextToSpeechProviders.ELEVEN_LABS.name:
            with col2:
                if not st.session_state.get("elevenlabs_api_key"):
                    st.session_state["elevenlabs_api_key"] = page.request.session.get(
                        SESSION_ELEVENLABS_API_KEY
                    )

                elevenlabs_use_custom_key = st.checkbox(
                    "Use custom API key + Voice ID",
                    value=bool(st.session_state.get("elevenlabs_api_key")),
                )
                if elevenlabs_use_custom_key:
                    st.session_state["elevenlabs_voice_name"] = None
                    elevenlabs_api_key = st.text_input(
                        """
                        ###### Your ElevenLabs API key
                        *Read <a target="_blank" href="https://docs.elevenlabs.io/api-reference/authentication">this</a>
                        to know how to obtain an API key from
                        ElevenLabs.*
                        """,
                        key="elevenlabs_api_key",
                    )

                    selected_voice_id = st.session_state.get("elevenlabs_voice_id")
                    elevenlabs_voices = (
                        {selected_voice_id: selected_voice_id}
                        if selected_voice_id
                        else {}
                    )

                    if elevenlabs_api_key:
                        try:
                            elevenlabs_voices = fetch_elevenlabs_voices(
                                elevenlabs_api_key
                            )
                        except requests.exceptions.HTTPError as e:
                            st.error(
                                f"Invalid ElevenLabs API key. Failed to fetch voices: {e}"
                            )

                    st.selectbox(
                        """
                        ###### Voice ID (ElevenLabs)
                        """,
                        key="elevenlabs_voice_id",
                        options=elevenlabs_voices.keys(),
                        format_func=elevenlabs_voices.__getitem__,
                    )
                else:
                    st.session_state["elevenlabs_api_key"] = None
                    st.session_state["elevenlabs_voice_id"] = None
                    if not (
                        page
                        and (
                            page.is_current_user_paying()
                            or page.is_current_user_admin()
                        )
                    ):
                        st.caption(
                            """
                            Note: Please purchase Gooey.AI credits to use ElevenLabs voices
                            <a href="/account">here</a>.<br/>
                            Alternatively, you can use your own ElevenLabs API key by selecting the checkbox above.
                            """
                        )

                    st.session_state.update(
                        elevenlabs_api_key=None, elevenlabs_voice_id=None
                    )
                    st.selectbox(
                        """
                        ###### Voice Name (ElevenLabs)
                        """,
                        key="elevenlabs_voice_name",
                        format_func=str,
                        options=ELEVEN_LABS_VOICES.keys(),
                    )

                page.request.session[SESSION_ELEVENLABS_API_KEY] = st.session_state.get(
                    "elevenlabs_api_key"
                )

                st.selectbox(
                    """
                    ###### Voice Model
                    """,
                    key="elevenlabs_model",
                    format_func=ELEVEN_LABS_MODELS.__getitem__,
                    options=ELEVEN_LABS_MODELS.keys(),
                )

            col1, col2 = st.columns(2)
            with col1:
                st.slider(
                    """
                    ###### Stability
                    *A lower stability provides a broader emotional range.
                    A value lower than 0.3 can lead to too much instability.
                    [Read more](https://docs.elevenlabs.io/speech-synthesis/voice-settings#stability).*
                    """,
                    min_value=0,
                    max_value=1.0,
                    step=0.05,
                    key="elevenlabs_stability",
                )
            with col2:
                st.slider(
                    """
                    ###### Similarity Boost
                    *Dictates how hard the model should try to replicate the original voice.
                    [Read more](https://docs.elevenlabs.io/speech-synthesis/voice-settings#similarity).*
                    """,
                    min_value=0,
                    max_value=1.0,
                    step=0.05,
                    key="elevenlabs_similarity_boost",
                )

            with st.expander(
                "Eleven Labs Supported Languages",
                style={"fontSize": "0.9rem", "textDecoration": "underline"},
            ):
                st.caption(
                    "With Multilingual V2 voice model", style={"fontSize": "0.8rem"}
                )
                st.caption(
                    ", ".join(ELEVEN_LABS_SUPPORTED_LANGS), style={"fontSize": "0.8rem"}
                )


@redis_cache_decorator
def google_tts_voices() -> dict[str, str]:
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


_elevenlabs_category_order = {
    "cloned": 1,
    "generated": 2,
    "premade": 3,
}


@st.cache_in_session_state
def fetch_elevenlabs_voices(api_key: str) -> dict[str, str]:
    r = requests.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"Accept": "application/json", "xi-api-key": api_key},
    )
    r.raise_for_status()
    print(r.json()["voices"])
    sorted_voices = sorted(
        r.json()["voices"],
        key=lambda v: (_elevenlabs_category_order.get(v["category"], 0), v["name"]),
    )
    return {
        v["voice_id"]: " - ".join([v["name"], *v["labels"].values()])
        for v in sorted_voices
    }
