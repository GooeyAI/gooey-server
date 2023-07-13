import json
import os.path
import subprocess
import tempfile
from enum import Enum

import requests
import typing_extensions
from furl import furl

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.gpu_server import (
    GpuEndpoints,
    call_celery_task,
)


SHORT_FILE_CUTOFF = 5 * 1024 * 1024  # 1 MB
TRANSLITERATION_SUPPORTED = ["ar", "bn", " gu", "hi", "ja", "kn", "ru", "ta", "te"]


class AsrModels(Enum):
    whisper_large_v2 = "Whisper Large v2 (openai)"
    whisper_hindi_large_v2 = "Whisper Hindi Large v2 (Bhashini)"
    whisper_telugu_large_v2 = "Whisper Telugu Large v2 (Bhashini)"
    nemo_english = "Conformer English (ai4bharat.org)"
    nemo_hindi = "Conformer Hindi (ai4bharat.org)"
    vakyansh_bhojpuri = "Vakyansh Bhojpuri (Open-Speech-EkStep)"
    usm = "USM (Google)"


forced_asr_languages = {
    AsrModels.whisper_hindi_large_v2: "hi",
    AsrModels.whisper_telugu_large_v2: "te",
    AsrModels.vakyansh_bhojpuri: "bho",
    AsrModels.nemo_english: "en",
    AsrModels.nemo_hindi: "hi",
}

asr_model_ids = {
    AsrModels.whisper_large_v2: "openai/whisper-large-v2",
    AsrModels.whisper_hindi_large_v2: "vasista22/whisper-hindi-large-v2",
    AsrModels.whisper_telugu_large_v2: "vasista22/whisper-telugu-large-v2",
    AsrModels.vakyansh_bhojpuri: "Harveenchadha/vakyansh-wav2vec2-bhojpuri-bhom-60",
    AsrModels.nemo_english: "https://objectstore.e2enetworks.net/indic-asr-public/checkpoints/conformer/english_large_data_fixed.nemo",
    AsrModels.nemo_hindi: "https://objectstore.e2enetworks.net/indic-asr-public/checkpoints/conformer/stt_hi_conformer_ctc_large_v2.nemo",
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
    from google.cloud import speech_v1p1beta1

    selected_model = AsrModels[selected_model]
    output_format = AsrOutputFormat[output_format]
    is_youtube_url = "youtube" in audio_url or "youtu.be" in audio_url
    if is_youtube_url:
        audio_url, size = download_youtube_to_wav(audio_url)
    else:
        audio_url, size = audio_to_wav(audio_url)
    is_short = size < SHORT_FILE_CUTOFF
    # call usm model
    if selected_model == AsrModels.usm:
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
            if language:
                kwargs["language"] = language.split("-")[0]
            else:
                kwargs["language"] = forced_asr_languages.get(selected_model)
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
            return data["text"]
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


# 16kHz, 16-bit, mono
FFMPEG_WAV_ARGS = ["-vn", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000"]


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
        and data["streams"][0]["codec_name"] == "pcm_s16le"
        and data["streams"][0]["channels"] == 1
        and data["streams"][0]["sample_rate"] == "16000"
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
