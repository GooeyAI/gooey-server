import os.path
import subprocess
import tempfile
from enum import Enum

import requests
import streamlit2 as st
from furl import furl
from google.cloud import speech_v1p1beta1
from google.cloud import translate, translate_v2

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.gpu_server import GpuEndpoints


class AsrModels(Enum):
    whisper_large_v2 = "Whisper Large v2 (openai)"
    whisper_hindi_large_v2 = "Whisper Hindi Large v2 (Bhashini)"
    nemo_english = "Conformer English (ai4bharat.org)"
    nemo_hindi = "Conformer Hindi (ai4bharat.org)"
    usm = "USM (Google)"


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
    audio_url: str,
    selected_model: str,
    language: str = None,
) -> str:
    """
    Run ASR on audio.
    Args:
        audio_url (str): url of audio to be transcribed.
        selected_model (str): ASR model to use.
        language: language of the audio
    Returns:
        str: Transcribed text.
    """
    selected_model = AsrModels[selected_model]
    is_youtube_url = "youtube" in audio_url or "youtu.be" in audio_url
    if is_youtube_url:
        audio_url = download_youtube_to_wav(audio_url)
    # call usm model
    if selected_model == AsrModels.usm:
        if not is_youtube_url:
            audio_url = audio_to_wav(audio_url)
        # Initialize request argument(s)
        config = speech_v1p1beta1.RecognitionConfig()
        config.language_code = language
        config.audio_channel_count = 1
        audio = speech_v1p1beta1.RecognitionAudio()
        audio.uri = "gs://" + "/".join(furl(audio_url).path.segments)
        request = speech_v1p1beta1.LongRunningRecognizeRequest(
            config=config, audio=audio
        )
        # Create a client
        client = speech_v1p1beta1.SpeechClient()
        # Make the request
        operation = client.long_running_recognize(request=request)
        # Wait for operation to complete
        response = operation.result()
        # Handle the response
        return "\n\n".join(
            result.alternatives[0].transcript for result in response.results
        )
    # call one of the self-hosted models
    if "whisper" in selected_model.name:
        if language:
            language = language.split("-")[0]
        elif "hindi" in selected_model.name:
            language = "hi"
        r = requests.post(
            str(GpuEndpoints.whisper),
            json={
                "pipeline": dict(
                    model_id=asr_model_ids[selected_model],
                ),
                "inputs": {
                    "audio": audio_url,
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
                    "audio": audio_url,
                },
            },
        )
    r.raise_for_status()
    return r.json()["text"]


def download_youtube_to_wav(youtube_url: str) -> str:
    """
    Convert a youtube video to wav audio file.
    Returns:
        str: url of the wav audio file.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        infile = os.path.join(tmpdir, "infile")
        outfile = os.path.join(tmpdir, "outfile.wav")
        # run yt-dlp to download audio
        args = [
            "yt-dlp",
            "--no-playlist",
            "--format",
            "bestaudio",
            "--output",
            infile,
            youtube_url,
        ]
        print("\t$", " ".join(args))
        subprocess.check_call(args)
        # convert audio to single channel wav
        args = ["ffmpeg", "-y", "-i", infile, "-ac", "1", outfile]
        print("\t$", " ".join(args))
        subprocess.check_call(args)
        # read wav file into memory
        with open(outfile, "rb") as f:
            wavdata = f.read()
    # upload the wav file
    return upload_file_from_bytes("yt_audio.wav", wavdata, "audio/wav")


def audio_to_wav(audio_url: str) -> str:
    with (
        tempfile.NamedTemporaryFile() as infile,
        tempfile.NamedTemporaryFile(suffix=".wav") as outfile,
    ):
        infile.write(requests.get(audio_url).content)
        infile.flush()
        args = ["ffmpeg", "-y", "-i", infile.name, "-ac", "1", outfile.name]
        print("\t$", " ".join(args))
        subprocess.check_call(args)
        wavdata = outfile.read()
    filename = furl(audio_url).path.segments[-1] + ".wav"
    return upload_file_from_bytes(filename, wavdata, "audio/wav")
