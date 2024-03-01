import datetime
from time import sleep

import requests
from furl import furl

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import (
    raise_for_status,
)
from daras_ai_v2.redis_cache import redis_cache_decorator

# 20 mins timeout
MAX_POLLS = 200
POLL_INTERVAL = 6


def azure_asr(audio_url: str, language: str):
    # Start by initializing a request
    # https://eastus.dev.cognitive.microsoft.com/docs/services/speech-to-text-api-v3-1/operations/Transcriptions_Create
    language = language or "en-US"
    r = requests.post(
        str(furl(settings.AZURE_SPEECH_ENDPOINT) / "speechtotext/v3.1/transcriptions"),
        headers=azure_auth_header(),
        json={
            "contentUrls": [audio_url],
            "displayName": f"Gooey Transcription {datetime.datetime.now().isoformat()} {language=} {audio_url=}",
            "model": azure_get_latest_model(language),
            "properties": {
                "wordLevelTimestampsEnabled": False,
                # "displayFormWordLevelTimestampsEnabled": True,
                # "diarizationEnabled": False,
                # "punctuationMode": "DictatedAndAutomatic",
                # "profanityFilterMode": "Masked",
            },
            "locale": language,
        },
    )
    raise_for_status(r)
    uri = r.json()["self"]

    # poll for results
    for _ in range(MAX_POLLS):
        r = requests.get(uri, headers=azure_auth_header())
        if not r.ok or not r.json()["status"] == "Succeeded":
            sleep(POLL_INTERVAL)
            continue
        r = requests.get(r.json()["links"]["files"], headers=azure_auth_header())
        raise_for_status(r)
        transcriptions = []
        for value in r.json()["values"]:
            if value["kind"] != "Transcription":
                continue
            r = requests.get(value["links"]["contentUrl"], headers=azure_auth_header())
            raise_for_status(r)
            combined_phrases = r.json().get("combinedRecognizedPhrases") or [{}]
            transcriptions += [combined_phrases[0].get("display", "")]
        return "\n".join(transcriptions)

    raise RuntimeError("Max polls exceeded, Azure speech did not yield a response")


@redis_cache_decorator(ex=settings.REDIS_MODELS_CACHE_EXPIRY)
def azure_get_latest_model(language: str) -> dict | None:
    # https://eastus.dev.cognitive.microsoft.com/docs/services/speech-to-text-api-v3-1/operations/Models_ListBaseModels
    r = requests.get(
        str(furl(settings.AZURE_SPEECH_ENDPOINT) / "speechtotext/v3.1/models/base"),
        headers=azure_auth_header(),
        params={"filter": f"locale eq '{language}'"},
    )
    raise_for_status(r)
    data = r.json()["values"]
    try:
        models = sorted(
            data,
            key=lambda m: datetime.datetime.strptime(
                m["createdDateTime"], "%Y-%m-%dT%H:%M:%SZ"
            ),
            reverse=True,
        )
    # ignore date parsing errors
    except ValueError:
        models = data
        models.reverse()
    for model in models:
        if "whisper" in model["displayName"].lower():
            # whisper is pretty slow on azure, so we ignore it
            continue
        # return the latest model
        return {"self": model["self"]}


def azure_auth_header():
    return {
        "Ocp-Apim-Subscription-Key": settings.AZURE_SPEECH_KEY,
    }
