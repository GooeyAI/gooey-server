from enum import Enum

import requests
import streamlit as st
from google.cloud import translate, translate_v2

from daras_ai_v2.gpu_server import GpuEndpoints


class AsrModels(Enum):
    whisper_large_v2 = "Whisper Large v2 (openai)"
    whisper_hindi_large_v2 = "Whisper Hindi Large v2 (Bhashini)"
    nemo_english = "Conformer English (ai4bharat.org)"
    nemo_hindi = "Conformer Hindi (ai4bharat.org)"


asr_model_ids = {
    AsrModels.whisper_large_v2: "openai/whisper-large-v2",
    AsrModels.whisper_hindi_large_v2: "vasista22/whisper-hindi-large-v2",
    AsrModels.nemo_english: "https://objectstore.e2enetworks.net/indic-asr-public/checkpoints/conformer/english_large_data_fixed.nemo",
    AsrModels.nemo_hindi: "https://objectstore.e2enetworks.net/indic-asr-public/checkpoints/conformer/stt_hi_conformer_ctc_large_v2.nemo",
}


def google_translate_language_selector(
    label="""
    ###### Google Translate (*optional*)
    """,
    key="google_translate_target",
):
    """
    Streamlit widget for selecting a language for Google Translate.
    Args:
        label: the label to display
        key: the key to save the selected language to in the session state
    """
    languages = google_translate_languages()
    options = list(languages.keys())
    options.insert(0, None)
    st.selectbox(
        label=label,
        key=key,
        format_func=lambda k: languages[k] if k else "———",
        options=options,
    )


@st.cache_data()
def google_translate_languages() -> dict[str, str]:
    """
    Get list of supported languages for Google Translate.
    :return: Dictionary of language codes and display names.
    """
    parent = f"projects/dara-c1b52/locations/global"
    client = translate.TranslationServiceClient()
    supported_languages = client.get_supported_languages(
        parent, display_language_code="en"
    )
    return {
        lang.language_code: lang.display_name
        for lang in supported_languages.languages
        if lang.support_target
    }


def run_google_translate(texts: list[str], google_translate_target: str) -> list[str]:
    """
    Translate text using the Google Translate API.
    Args:
        texts (list[str]): Text to be translated.
        google_translate_target (str): Language code to translate to.
    Returns:
        list[str]: Translated text.
    """
    translate_client = translate_v2.Client()
    result = translate_client.translate(
        texts, target_language=google_translate_target, format_="text"
    )
    return [r["translatedText"] for r in result]


def run_asr(
    audio: str,
    selected_model: str,
) -> str:
    """
    Run ASR on audio.
    Args:
        audio (str): Audio to be transcribed.
        selected_model (str): ASR model to use.
    Returns:
        str: Transcribed text.
    """
    selected_model = AsrModels[selected_model]
    if "hindi" in selected_model.name:
        language = "hindi"
    else:
        language = "english"
    if "whisper" in selected_model.name:
        r = requests.post(
            str(GpuEndpoints.whisper),
            json={
                "pipeline": dict(
                    model_id=asr_model_ids[selected_model],
                ),
                "inputs": {
                    "audio": audio,
                    "task": "transcribe",
                    "language": language,
                },
            },
        )
    else:
        r = requests.post(
            str(GpuEndpoints.nemo_asr),
            json={
                "pipeline": dict(
                    model_id=asr_model_ids[selected_model],
                ),
                "inputs": {
                    "audio": audio,
                },
            },
        )
    r.raise_for_status()
    return r.json()["text"]
