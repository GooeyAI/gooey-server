from enum import Enum
import typing

import requests
from furl import furl
from daras_ai_v2.azure_asr import azure_auth_header

import gooey_ui as st
from daras_ai_v2 import settings
from daras_ai_v2.custom_enum import GooeyEnum
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.exceptions import raise_for_status
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


class OpenAI_TTS_Models(GooeyEnum):
    tts_1 = "tts-1"
    tts_1_hd = "tts-1-hd"


class OpenAI_TTS_Voices(GooeyEnum):
    alloy = "alloy"
    echo = "echo"
    fable = "fable"
    onyx = "onyx"
    nova = "nova"
    shimmer = "shimmer"


class TextToSpeechProviders(Enum):
    GOOGLE_TTS = "Google Text-to-Speech"
    ELEVEN_LABS = "Eleven Labs"
    UBERDUCK = "Uberduck.ai"
    BARK = "Bark (suno-ai)"
    AZURE_TTS = "Azure Text-to-Speech"
    OPEN_AI = "OpenAI"


# This exists only for backwards compatiblity
OLD_ELEVEN_LABS_VOICES = { "Rachel": "21m00Tcm4TlvDq8ikWAM", "Clyde": "2EiwWnXFnvU5JabPnv8n", "Domi": "AZnzlk1XvdvUeBnXmlld", "Dave": "CYw3kZ02Hs0563khs1Fj", "Fin": "D38z5RcWu1voky8WS1ja", "Bella": "EXAVITQu4vr4xnSDxMaL", "Antoni": "ErXwobaYiN019PkySvjV", "Thomas": "GBv7mTt0atIp3Br8iCZE", "Charlie": "IKne3meq5aSn9XLyUdCD", "Emily": "LcfcDJNUP1GQjkzn1xUU", "Elli": "MF3mGyEYCl7XYWbV9V6O", "Callum": "N2lVS1w4EtoT3dr4eOWO", "Patrick": "ODq5zmih8GrVes37Dizd", "Harry": "SOYHLrjzK2X1ezoPC6cr", "Liam": "TX3LPaxmHKxFdv7VOQHJ", "Dorothy": "ThT5KcBeYPX3keUQqHPh", "Josh": "TxGEqnHWrfWFTfGW9XjX", "Arnold": "VR6AewLTigWG4xSOukaG", "Charlotte": "XB0fDUnXU5powFXDhCwa", "Matilda": "XrExE9yKIg1WjnnlVkGX", "Matthew": "Yko7PKHZNXotIFUBG7I9", "James": "ZQe5CZNOzWyzPSCn5a3c", "Joseph": "Zlb1dXrM653N07WRdFW3", "Jeremy": "bVMeCyTHy58xNoL34h3p", "Michael": "flq6f7yk4E4fJM5XTYuZ", "Ethan": "g5CIjZEefAph4nQFvHAz", "Gigi": "jBpfuIE2acCO8z3wKNLl", "Freya": "jsCqWAovK2LkecY7zXl4", "Grace": "oWAxZDx7w5VEj9dCyTzz", "Daniel": "onwK4e9ZLuTAKqWW03F9", "Serena": "pMsXgVXv3BLzUgSXRplE", "Adam": "pNInz6obpgDQGcFmaJgB", "Nicole": "piTKgcLEGmPE4e6mEKli", "Jessie": "t0jbNlBVZ17f02VDIeMI", "Ryan": "wViXBPUzp2ZZixB1xQuM", "Sam": "yoZ06aMxZJJ28mfd3POQ", "Glinda": "z9fAnlkpzviPz146aGWa", "Giovanni": "zcAOhNBS3c14rBihAFp1", "Mimi": "zrHiDhphv9ZnVXBqCLjz" }  # fmt:skip


@redis_cache_decorator(ex=settings.REDIS_MODELS_CACHE_EXPIRY)
def default_elevenlabs_voices() -> dict[str, str]:
    return fetch_elevenlabs_voices(settings.ELEVEN_LABS_API_KEY)


ELEVEN_LABS_MODELS = {
    "eleven_multilingual_v2": "Multilingual V2 - High quality speech in 29 languages",
    "eleven_turbo_v2": "English V2 - Very low latency text-to-speech",
    "eleven_monolingual_v1": "English V1 - Low latency text-to-speech",
    "eleven_multilingual_v1": "Multilingual V1",
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


def text_to_speech_provider_selector(page):
    col1, col2 = st.columns(2)
    with col1:
        tts_provider = enum_selector(
            TextToSpeechProviders,
            "###### Text-to-Speech Provider",
            key="tts_provider",
            use_selectbox=True,
        )
    with col2:
        match tts_provider:
            case TextToSpeechProviders.BARK.name:
                bark_selector()
            case TextToSpeechProviders.GOOGLE_TTS.name:
                google_tts_selector()
            case TextToSpeechProviders.UBERDUCK.name:
                uberduck_selector()
            case TextToSpeechProviders.ELEVEN_LABS.name:
                elevenlabs_selector(page)
            case TextToSpeechProviders.AZURE_TTS.name:
                azure_tts_selector()
            case TextToSpeechProviders.OPEN_AI.name:
                openai_tts_selector()
    return tts_provider


def text_to_speech_settings(page, tts_provider):
    match tts_provider:
        case TextToSpeechProviders.BARK.name:
            pass
        case TextToSpeechProviders.GOOGLE_TTS.name:
            google_tts_settings()
        case TextToSpeechProviders.UBERDUCK.name:
            uberduck_settings()
        case TextToSpeechProviders.ELEVEN_LABS.name:
            elevenlabs_settings()
        case TextToSpeechProviders.AZURE_TTS.name:
            azure_tts_settings()
        case TextToSpeechProviders.OPEN_AI.name:
            openai_tts_settings()


def openai_tts_selector():
    enum_selector(
        OpenAI_TTS_Voices,
        label="###### OpenAI Voice Name",
        key="openai_voice_name",
        use_selectbox=True,
    )


def openai_tts_settings():
    enum_selector(
        OpenAI_TTS_Models,
        label="###### OpenAI TTS Model",
        key="openai_tts_model",
        use_selectbox=True,
    )
    st.caption(
        "The HD version has less static noise in most situations at the cost of higher latency. Read more about the OpenAI voices and models [here](https://platform.openai.com/docs/guides/text-to-speech)."
    )


def azure_tts_selector():
    if settings.AZURE_SPEECH_KEY:
        voices = azure_tts_voices()
    else:
        voices = {}
    st.selectbox(
        label="""
        ###### Azure TTS Voice name
        """,
        key="azure_voice_name",
        format_func=lambda voice: f"{voices[voice].get('DisplayName')} - {voices[voice].get('LocaleName')}",
        options=voices.keys(),
    )


def azure_tts_settings():
    voice_name = st.session_state.get("azure_voice_name")
    if not voice_name or not settings.AZURE_SPEECH_KEY:
        return
    try:
        voice = azure_tts_voices()[voice_name]
    except KeyError:
        return
    st.markdown(
        f"""
        ###### {voice.get('Name')}:
        * Name: {voice.get('LocalName')} {'(' + str(voice.get('DisplayName')) + ')' if voice.get('LocalName') != voice.get('DisplayName') else ''}
        * Gender: {voice.get('Gender')}
        * Locale: {voice.get('LocaleName')}
        * Locale Code: {voice.get('Locale')}
        * Sample Rate: {voice.get('SampleRateHertz')} Hz
        * Voice Type: {voice.get('VoiceType')}
        * Words Per Minute: {voice.get('WordsPerMinute')}

        See all the supported languages and voices [here](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts).
        """
    )


@redis_cache_decorator(ex=settings.REDIS_MODELS_CACHE_EXPIRY)
def azure_tts_voices() -> dict[str, dict[str, str]]:
    # E.g., {"af-ZA-AdriNeural": {
    #     "Name": "Microsoft Server Speech Text to Speech Voice (af-ZA, AdriNeural)",
    #     "DisplayName": "Adri",
    #     "LocalName": "Adri",
    #     "ShortName": "af-ZA-AdriNeural",
    #     "Gender": "Female",
    #     "Locale": "af-ZA",
    #     "LocaleName": "Afrikaans (South Africa)",
    #     "SampleRateHertz": "48000",
    #     "VoiceType": "Neural",
    #     "Status": "GA",
    #     "WordsPerMinute": "147",
    # }}
    res = requests.get(
        str(furl(settings.AZURE_TTS_ENDPOINT) / "/cognitiveservices/voices/list"),
        headers=azure_auth_header(),
    )
    raise_for_status(res)
    return {voice.get("ShortName", "Unknown"): voice for voice in res.json()}


def bark_selector():
    st.selectbox(
        label="""
        ###### Bark History Prompt
        """,
        key="bark_history_prompt",
        format_func=BARK_ALLOWED_PROMPTS.__getitem__,
        options=BARK_ALLOWED_PROMPTS.keys(),
    )


def google_tts_selector():
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


def google_tts_settings():
    st.write(f"##### 🗣️ {TextToSpeechProviders.GOOGLE_TTS.value} Settings")
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


def uberduck_selector():
    st.selectbox(
        label="""
        ###### Voice name (Uberduck)
        """,
        key="uberduck_voice_name",
        format_func=lambda option: f"{option}",
        options=UBERDUCK_VOICES.keys(),
    )


def uberduck_settings():
    st.write(f"##### 🗣️ {TextToSpeechProviders.UBERDUCK.value} Settings")
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


def elevenlabs_selector(page):
    if not st.session_state.get("elevenlabs_api_key"):
        st.session_state["elevenlabs_api_key"] = page.request.session.get(
            SESSION_ELEVENLABS_API_KEY
        )

    # for backwards compat
    if old_voice_name := st.session_state.pop("elevenlabs_voice_name", None):
        try:
            st.session_state["elevenlabs_voice_id"] = OLD_ELEVEN_LABS_VOICES[
                old_voice_name
            ]
        except KeyError:
            pass

    elevenlabs_use_custom_key = st.checkbox(
        "Use custom API key + Voice ID",
        value=bool(st.session_state.get("elevenlabs_api_key")),
    )
    if elevenlabs_use_custom_key:
        elevenlabs_api_key = st.text_input(
            """
            ###### Your ElevenLabs API key
            *Read <a target="_blank" href="https://docs.elevenlabs.io/api-reference/authentication">this</a>
            to know how to obtain an API key from
            ElevenLabs.*
            """,
            key="elevenlabs_api_key",
        )
        if elevenlabs_api_key:
            try:
                voices = fetch_elevenlabs_voices(elevenlabs_api_key)
            except requests.exceptions.HTTPError as e:
                st.error(f"Invalid ElevenLabs API key. Failed to fetch voices: {e}")
                return
            selected_voice_id = st.session_state.get("elevenlabs_voice_id")
            if selected_voice_id and selected_voice_id not in voices:
                voices[selected_voice_id] = selected_voice_id
        else:
            voices = {}
    else:
        st.session_state["elevenlabs_api_key"] = None
        if not (
            page and (page.is_current_user_paying() or page.is_current_user_admin())
        ):
            st.caption(
                """
                Note: Please purchase Gooey.AI credits to use ElevenLabs voices [here](/account).
                Alternatively, you can use your own ElevenLabs API key by selecting the checkbox above.
                """
            )
        if settings.ELEVEN_LABS_API_KEY:
            voices = default_elevenlabs_voices()
        else:
            voices = {}

    page.request.session[SESSION_ELEVENLABS_API_KEY] = st.session_state.get(
        "elevenlabs_api_key"
    )
    st.selectbox(
        """
        ###### Voice
        """,
        key="elevenlabs_voice_id",
        options=voices.keys(),
        format_func=voices.__getitem__,
    )
    st.selectbox(
        """
        ###### Model
        """,
        key="elevenlabs_model",
        format_func=ELEVEN_LABS_MODELS.__getitem__,
        options=ELEVEN_LABS_MODELS.keys(),
    )


def elevenlabs_settings():
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

    if st.session_state.get("elevenlabs_model") == "eleven_multilingual_v2":
        col1, col2 = st.columns(2)
        with col1:
            st.slider(
                """
                ###### Style Exaggeration
                """,
                min_value=0,
                max_value=1.0,
                step=0.05,
                key="elevenlabs_style",
            )
        with col2:
            st.checkbox(
                "Speaker Boost",
                key="elevenlabs_speaker_boost",
                value=True,
            )

    with st.expander(
        "Eleven Labs Supported Languages",
        style={"fontSize": "0.9rem", "textDecoration": "underline"},
    ):
        st.caption("With Multilingual V2 voice model", style={"fontSize": "0.8rem"})
        st.caption(", ".join(ELEVEN_LABS_SUPPORTED_LANGS), style={"fontSize": "0.8rem"})


@redis_cache_decorator(ex=settings.REDIS_MODELS_CACHE_EXPIRY)
def google_tts_voices() -> dict[str, str]:
    from google.cloud import texttospeech

    voices: list[texttospeech.Voice] = list(
        texttospeech.TextToSpeechClient().list_voices().voices
    )
    voices.sort(key=_voice_sort_key)
    return {voice.name: _pretty_voice(voice) for voice in voices}


def _pretty_voice(voice) -> str:
    return f"{voice.name} ({voice.ssml_gender.name.capitalize()})"


_lang_code_sort = ["en-US", "en-IN", "en-GB", "en-AU"]


def _voice_sort_key(voice: "texttospeech.Voice"):
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
    raise_for_status(r)
    sorted_voices = sorted(
        r.json()["voices"],
        key=lambda v: (_elevenlabs_category_order.get(v["category"], 0), v["name"]),
    )
    return {
        v["voice_id"]: " - ".join([v["name"], *v["labels"].values()])
        for v in sorted_voices
    }
