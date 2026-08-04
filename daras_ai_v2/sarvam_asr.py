import time

import requests

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import UserError, raise_for_status

SAARAS_V3_BATCH_MAX_POLLS = 360
SAARAS_V3_BATCH_POLL_INTERVAL_SECONDS = 5
SARVAM_ASR_BASE_URL = "https://api.sarvam.ai/speech-to-text"


def sarvam_saaras_v3_asr(
    *,
    audio_url: str,
    language_code: str,
    mode: str,
    with_timestamps: bool,
) -> dict:
    if not settings.SARVAM_API_KEY:
        raise UserError(
            "Sarvam AI ASR is not configured: missing SARVAM_API_KEY"
        )

    audio_response = requests.get(audio_url)
    raise_for_status(audio_response, is_user_url=True)

    result = _sarvam_saaras_v3_batch_asr(
        audio=audio_response.content,
        language_code=language_code,
        mode=mode,
        with_timestamps=with_timestamps,
    )
    return {
        "text": result["transcript"].strip(),
        "chunks": _sarvam_timestamps_to_chunks(result.get("timestamps")),
    }


def _sarvam_saaras_v3_batch_asr(
    *,
    audio: bytes,
    language_code: str,
    mode: str,
    with_timestamps: bool,
) -> dict:
    headers = {"api-subscription-key": settings.SARVAM_API_KEY}
    filename = "audio.wav"

    response = requests.post(
        f"{SARVAM_ASR_BASE_URL}/job/v1",
        headers=headers,
        json={
            "job_parameters": {
                "model": "saaras:v3",
                "mode": mode,
                "language_code": language_code,
                "with_timestamps": with_timestamps,
            }
        },
    )
    raise_for_status(response)
    job_id = response.json()["job_id"]

    response = requests.post(
        f"{SARVAM_ASR_BASE_URL}/job/v1/upload-files",
        headers=headers,
        json={"job_id": job_id, "files": [filename]},
    )
    raise_for_status(response)
    upload_url = response.json()["upload_urls"][filename]["file_url"]

    response = requests.put(
        upload_url,
        headers={"Content-Type": "audio/wav", "x-ms-blob-type": "BlockBlob"},
        data=audio,
    )
    raise_for_status(response)

    response = requests.post(
        f"{SARVAM_ASR_BASE_URL}/job/v1/{job_id}/start",
        headers=headers,
    )
    raise_for_status(response)

    status = _wait_for_sarvam_batch_job(job_id=job_id, headers=headers)
    output_filenames = [
        output["file_name"]
        for detail in status.get("job_details", [])
        if detail.get("state") == "Success"
        for output in detail.get("outputs", [])
    ]
    if not output_filenames:
        error = next(
            (
                detail.get("error_message")
                for detail in status.get("job_details", [])
                if detail.get("error_message")
            ),
            None,
        )
        raise UserError(error or "Sarvam AI did not produce a transcription.")

    response = requests.post(
        f"{SARVAM_ASR_BASE_URL}/job/v1/download-files",
        headers=headers,
        json={"job_id": job_id, "files": output_filenames},
    )
    raise_for_status(response)
    download_url = response.json()["download_urls"][output_filenames[0]]["file_url"]

    response = requests.get(download_url)
    raise_for_status(response)
    return response.json()


def _wait_for_sarvam_batch_job(*, job_id: str, headers: dict[str, str]) -> dict:
    status_url = f"{SARVAM_ASR_BASE_URL}/job/v1/{job_id}/status"
    for _ in range(SAARAS_V3_BATCH_MAX_POLLS):
        response = requests.get(status_url, headers=headers)
        raise_for_status(response)
        status = response.json()
        job_state = status["job_state"]
        if job_state in {"Completed", "PartiallyCompleted"}:
            return status
        if job_state == "Failed":
            raise UserError(
                status.get("error_message") or "Sarvam AI transcription failed."
            )
        time.sleep(SAARAS_V3_BATCH_POLL_INTERVAL_SECONDS)

    raise TimeoutError("Sarvam AI batch transcription timed out.")


def _sarvam_timestamps_to_chunks(timestamps: dict | None) -> list[dict]:
    if not timestamps:
        return []
    texts = timestamps.get("chunks") or timestamps.get("words", [])
    return [
        {
            "text": text,
            "timestamp": (start, end),
            "speaker": None,
        }
        for text, start, end in zip(
            texts,
            timestamps.get("start_time_seconds", []),
            timestamps.get("end_time_seconds", []),
        )
    ]
