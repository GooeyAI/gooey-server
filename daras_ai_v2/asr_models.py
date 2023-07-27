import json
import os.path
import subprocess
import tempfile
from enum import Enum

import langcodes
import requests
import typing_extensions
from furl import furl

import gooey_ui as st
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.google_auth import get_google_auth_session
from daras_ai_v2.gpu_server import (
    GpuEndpoints,
    call_celery_task,
)

SHORT_FILE_CUTOFF = 5 * 1024 * 1024  # 1 MB

# below list was found experimentally since the supported languages list by google is actually wrong:
CHIRP_SUPPORTED = {"af-ZA", "sq-AL", "am-ET", "ar-EG", "hy-AM", "as-IN", "ast-ES", "az-AZ", "eu-ES", "be-BY", "bs-BA",
                   "bg-BG", "my-MM", "ca-ES", "ceb-PH", "ckb-IQ", "zh-Hans-CN", "yue-Hant-HK", "hr-HR", "cs-CZ",
                   "da-DK", "nl-NL", "en-AU", "en-IN", "en-GB", "en-US", "et-EE", "fil-PH", "fi-FI", "fr-CA", "fr-FR",
                   "gl-ES", "ka-GE", "de-DE", "el-GR", "gu-IN", "ha-NG", "iw-IL", "hi-IN", "hu-HU", "is-IS", "id-ID",
                   "it-IT", "ja-JP", "jv-ID", "kea-CV", "kam-KE", "kn-IN", "kk-KZ", "km-KH", "ko-KR", "ky-KG", "lo-LA",
                   "lv-LV", "ln-CD", "lt-LT", "luo-KE", "lb-LU", "mk-MK", "ms-MY", "ml-IN", "mt-MT", "mi-NZ", "mr-IN",
                   "mn-MN", "ne-NP", "ny-MW", "oc-FR", "ps-AF", "fa-IR", "pl-PL", "pt-BR", "pa-Guru-IN", "ro-RO",
                   "ru-RU", "nso-ZA", "sr-RS", "sn-ZW", "sd-IN", "si-LK", "sk-SK", "sl-SI", "so-SO", "es-ES", "es-US",
                   "su-ID", "sw", "sv-SE", "tg-TJ", "ta-IN", "te-IN", "th-TH", "tr-TR", "uk-UA", "ur-PK", "uz-UZ",
                   "vi-VN", "cy-GB", "wo-SN", "yo-NG", "zu-ZA"}  # fmt: skip

WHISPER_SUPPORTED = {"af", "ar", "hy", "az", "be", "bs", "bg", "ca", "zh", "hr", "cs", "da", "nl", "en", "et", "fi",
                     "fr", "gl", "de", "el", "he", "hi", "hu", "is", "id", "it", "ja", "kn", "kk", "ko", "lv", "lt",
                     "mk", "ms", "mr", "mi", "ne", "no", "fa", "pl", "pt", "ro", "ru", "sr", "sk", "sl", "es", "sw",
                     "sv", "tl", "ta", "th", "tr", "uk", "ur", "vi", "cy"}  # fmt: skip

# 16kHz, 16-bit, mono
WAV_SR = 16_000
WAV_CODEC = "pcm_s16le"
WAV_CHANNELS = 1
FFMPEG_WAV_ARGS = [
    "-vn",
    "-acodec", WAV_CODEC,
    "-ac", str(WAV_CHANNELS),
    "-ar", str(WAV_SR),
]  # fmt: skip


class AsrModels(Enum):
    whisper_large_v2 = "Whisper Large v2 (openai)"
    whisper_hindi_large_v2 = "Whisper Hindi Large v2 (Bhashini)"
    whisper_telugu_large_v2 = "Whisper Telugu Large v2 (Bhashini)"
    nemo_english = "Conformer English (ai4bharat.org)"
    nemo_hindi = "Conformer Hindi (ai4bharat.org)"
    vakyansh_bhojpuri = "Vakyansh Bhojpuri (Open-Speech-EkStep)"
    usm = "Chirp / USM (Google)"


asr_model_ids = {
    AsrModels.whisper_large_v2: "openai/whisper-large-v2",
    AsrModels.whisper_hindi_large_v2: "vasista22/whisper-hindi-large-v2",
    AsrModels.whisper_telugu_large_v2: "vasista22/whisper-telugu-large-v2",
    AsrModels.vakyansh_bhojpuri: "Harveenchadha/vakyansh-wav2vec2-bhojpuri-bhom-60",
    AsrModels.nemo_english: "https://objectstore.e2enetworks.net/indic-asr-public/checkpoints/conformer/english_large_data_fixed.nemo",
    AsrModels.nemo_hindi: "https://objectstore.e2enetworks.net/indic-asr-public/checkpoints/conformer/stt_hi_conformer_ctc_large_v2.nemo",
}

forced_asr_languages = {
    AsrModels.whisper_hindi_large_v2: "hi",
    AsrModels.whisper_telugu_large_v2: "te",
    AsrModels.vakyansh_bhojpuri: "bho",
    AsrModels.nemo_english: "en",
    AsrModels.nemo_hindi: "hi",
}

asr_supported_languages = {
    AsrModels.whisper_large_v2: WHISPER_SUPPORTED,
    AsrModels.usm: CHIRP_SUPPORTED,
}


class AsrChunk(typing_extensions.TypedDict):
    timestamp: tuple[float, float]
    text: str


class AsrOutputJson(typing_extensions.TypedDict):
    text: str
    chunks: typing_extensions.NotRequired[list[AsrChunk]]


class AsrOutputFormat(Enum):
    text = "Text"
    json = "JSON"
    srt = "SRT"
    vtt = "VTT"


def asr_language_selector(
    selected_model: AsrModels,
    label="##### Spoken Language",
    key="language",
):
    # don't show language selector for models with forced language
    forced_lang = forced_asr_languages.get(selected_model)
    if forced_lang:
        st.session_state[key] = forced_lang
        return forced_lang

    options = [None, *asr_supported_languages.get(selected_model, [])]

    # handle non-canonical language codes
    old_val = st.session_state.get(key)
    if old_val and old_val not in options:
        lobj = langcodes.Language.get(old_val)
        for opt in options:
            if opt and langcodes.Language.get(opt).language == lobj.language:
                st.session_state[key] = opt
                break

    return st.selectbox(
        label=label,
        key=key,
        format_func=lambda l: (
            f"{langcodes.Language.get(l).display_name()} | {l}" if l else "Auto Detect"
        ),
        options=options,
    )


def run_asr(
    audio_url: str,
    selected_model: str,
    language: str = None,
    output_format: str = "text",
) -> str | AsrOutputJson:
    """
    Run ASR on audio.
    Args:
        audio_url (str): url of audio to be transcribed.
        selected_model (str): ASR model to use.
        language: language of the audio
        output_format: format of the output
    Returns:
        str: Transcribed text.
    """
    import google.cloud.speech_v2 as cloud_speech
    from google.api_core.client_options import ClientOptions
    from google.cloud.texttospeech_v1 import AudioEncoding

    selected_model = AsrModels[selected_model]
    output_format = AsrOutputFormat[output_format]
    is_youtube_url = "youtube" in audio_url or "youtu.be" in audio_url
    if is_youtube_url:
        audio_url, size = download_youtube_to_wav(audio_url)
    else:
        audio_url, size = audio_to_wav(audio_url)
    is_short = size < SHORT_FILE_CUTOFF
    if selected_model == AsrModels.usm:
        # note: only us-central1 and a few other regions support chirp recognizers (so global can't be used)
        location = "us-central1"

        # Create a client
        options = ClientOptions(api_endpoint=f"{location}-speech.googleapis.com")
        client = cloud_speech.SpeechClient(client_options=options)

        # preprocess language into BCP-47 code to avoid generating multiple recognizers for the same languages
        if language:
            lobj = langcodes.Language.get(language.strip())
            assert lobj.is_valid(), f"Invalid language: {language!r}"
            language = lobj.to_tag()
            assert language in CHIRP_SUPPORTED, f"Unsupported language: {language!r}"
        else:
            language = None

        recognizer = _get_or_create_recognizer(client, language, location)

        # Initialize request argument(s)
        config = cloud_speech.RecognitionConfig()
        if language:
            config.language_codes = [language]
        else:
            config.language_codes = CHIRP_SUPPORTED  # pick from supported langauges
            config.model = "chirp"  # use chirp model
        config.explicit_decoding_config = cloud_speech.ExplicitDecodingConfig(
            encoding=AudioEncoding.LINEAR16,
            sample_rate_hertz=WAV_SR,
            audio_channel_count=WAV_CHANNELS,
        )
        audio = cloud_speech.BatchRecognizeFileMetadata()
        audio.uri = "gs://" + "/".join(furl(audio_url).path.segments)
        # Specify that results should be inlined in the response (only possible for 1 audio file)
        output_config = cloud_speech.RecognitionOutputConfig()
        output_config.inline_response_config = cloud_speech.InlineOutputConfig()
        request = cloud_speech.BatchRecognizeRequest(
            recognizer=recognizer,
            config=config,
            files=[audio],
            recognition_output_config=output_config,
        )

        # Make the request
        operation = client.batch_recognize(request=request)
        # Wait for operation to complete
        response = operation.result()  # BatchRecognizeFileResult
        # Handle the response
        return "\n\n".join(
            result.alternatives[0].transcript
            for batch in response.results.values()  # BatchRecognizeResults
            for result in batch.transcript.results  # SpeechRecognitionResult
            if result.alternatives
        )
    elif "nemo" in selected_model.name:
        r = requests.post(
            str(GpuEndpoints.nemo_asr),
            json={
                "pipeline": dict(
                    model_id=asr_model_ids[selected_model],
                ),
                "inputs": dict(
                    audio=audio_url,
                ),
            },
        )
        r.raise_for_status()
        data = r.json()
    # check if we should use the fast queue
    # call one of the self-hosted models
    else:
        kwargs = {}
        if "vakyansh" in selected_model.name:
            # fixes https://github.com/huggingface/transformers/issues/15275#issuecomment-1624879632
            kwargs["decoder_kwargs"] = dict(skip_special_tokens=True)
            kwargs["chunk_length_s"] = 60
            kwargs["stride_length_s"] = (6, 0)
            kwargs["batch_size"] = 32
        elif "whisper" in selected_model.name:
            forced_lang = forced_asr_languages.get(selected_model)
            if forced_lang:
                kwargs["language"] = forced_lang
            elif language:
                lobj = langcodes.Language.get(language.strip())
                assert lobj.is_valid(), f"Invalid language: {language!r}"
                kwargs["language"] = lobj.language
        data = call_celery_task(
            "whisper",
            pipeline=dict(
                model_id=asr_model_ids[selected_model],
            ),
            inputs=dict(
                audio=audio_url,
                task="transcribe",
                return_timestamps=output_format != AsrOutputFormat.text,
                **kwargs,
            ),
            queue_prefix="gooey-gpu/short" if is_short else "gooey-gpu/long",
        )
    match output_format:
        case AsrOutputFormat.text:
            return data["text"].strip()
        case AsrOutputFormat.json:
            return data
        case AsrOutputFormat.srt:
            assert data.get("chunks"), f"{selected_model.value} can't generate SRT"
            return generate_srt(data["chunks"])
        case AsrOutputFormat.vtt:
            assert data.get("chunks"), f"{selected_model.value} can't generate VTT"
            return generate_vtt(data["chunks"])
        case _:
            raise ValueError(f"Invalid output format: {output_format}")


def _get_or_create_recognizer(
    client: "google.cloud.speech_v2.SpeechClient", language: str | None, location: str
) -> str:
    import google.api_core.exceptions
    import google.cloud.speech_v2 as cloud_speech

    _, project = get_google_auth_session()
    if language:
        recognizer_id = f"chirp-api--{language.lower()}"
        try:
            # check if recognizer already exists
            recognizer = client.get_recognizer(
                name=f"projects/{project}/locations/{location}/recognizers/{recognizer_id}"
            ).name
        except google.api_core.exceptions.NotFound:
            # create recognizer if it doesn't exist
            recognizer = (
                client.create_recognizer(
                    parent=f"projects/{project}/locations/{location}",
                    recognizer_id=recognizer_id,
                    recognizer=cloud_speech.Recognizer(
                        language_codes=[language], model="chirp"
                    ),
                )
                .result()
                .name
            )
    else:
        # no language provided => use default implicit recognizer
        recognizer = f"projects/{project}/locations/{location}/recognizers/_"
    return recognizer


def download_youtube_to_wav(youtube_url: str) -> tuple[str, int]:
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
        print("\t$ " + " ".join(args))
        subprocess.check_call(args)
        # convert audio to single channel wav
        args = ["ffmpeg", "-y", "-i", infile, *FFMPEG_WAV_ARGS, outfile]
        print("\t$ " + " ".join(args))
        subprocess.check_call(args)
        # read wav file into memory
        with open(outfile, "rb") as f:
            wavdata = f.read()
    # upload the wav file
    return upload_file_from_bytes("yt_audio.wav", wavdata, "audio/wav"), len(wavdata)


def audio_to_wav(audio_url: str) -> tuple[str, int]:
    with tempfile.NamedTemporaryFile() as infile:
        r = requests.get(audio_url)
        r.raise_for_status()
        infile.write(r.content)
        infile.flush()

        if check_wav_audio_format(infile.name):
            # already a wav file
            return audio_url, os.path.getsize(infile.name)

        with tempfile.NamedTemporaryFile(suffix=".wav") as outfile:
            # convert audio to single channel wav
            args = ["ffmpeg", "-y", "-i", infile.name, *FFMPEG_WAV_ARGS, outfile.name]
            print("\t$ " + " ".join(args))
            subprocess.check_call(args)
            wavdata = outfile.read()

    filename = furl(audio_url.strip("/")).path.segments[-1] + ".wav"
    return upload_file_from_bytes(filename, wavdata, "audio/wav"), len(wavdata)


def check_wav_audio_format(filename: str) -> bool:
    args = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        filename,
    ]
    print("\t$ " + " ".join(args))
    data = json.loads(subprocess.check_output(args))
    return (
        len(data["streams"]) == 1
        and data["streams"][0]["codec_name"] == WAV_CODEC
        and int(data["streams"][0]["channels"]) == WAV_CHANNELS
        and int(data["streams"][0]["sample_rate"]) == WAV_SR
    )


# code stolen from https://github.com/openai/whisper/blob/248b6cb124225dd263bb9bd32d060b6517e067f8/whisper/utils.py#L239
#


def generate_vtt(chunks: list[AsrChunk]):
    vtt = "WEBVTT\n"
    subs = iterate_subtitles(chunks, always_include_hours=False, decimal_marker=".")
    for start, end, text in subs:
        vtt += f"{start} --> {end}\n{text}\n\n"
    return vtt


def generate_srt(chunks: list[AsrChunk]):
    srt = ""
    subs = iterate_subtitles(chunks, always_include_hours=True, decimal_marker=",")
    for i, (start, end, text) in enumerate(subs, start=1):
        srt += f"{i}\n{start} --> {end}\n{text}\n\n"
    return srt


def iterate_subtitles(
    chunks: list[AsrChunk], always_include_hours: bool, decimal_marker: str
):
    for chunk in chunks:
        segment_start = format_timestamp(
            chunk["timestamp"][0], always_include_hours, decimal_marker
        )
        segment_end = format_timestamp(
            chunk["timestamp"][1], always_include_hours, decimal_marker
        )
        segment_text = chunk["text"].strip().replace("-->", "->")
        yield segment_start, segment_end, segment_text


def format_timestamp(seconds: float, always_include_hours: bool, decimal_marker: str):
    assert seconds >= 0, "non-negative timestamp expected"
    milliseconds = round(seconds * 1000.0)

    hours = milliseconds // 3_600_000
    milliseconds -= hours * 3_600_000

    minutes = milliseconds // 60_000
    milliseconds -= minutes * 60_000

    seconds = milliseconds // 1_000
    milliseconds -= seconds * 1_000

    hours_marker = f"{hours:02d}:" if always_include_hours or hours > 0 else ""
    return (
        f"{hours_marker}{minutes:02d}:{seconds:02d}{decimal_marker}{milliseconds:03d}"
    )
