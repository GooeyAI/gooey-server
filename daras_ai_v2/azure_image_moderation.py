from typing import Any

from furl import furl
import requests

from daras_ai_v2 import settings


def get_auth_headers():
    return {"Ocp-Apim-Subscription-Key": settings.AZURE_IMAGE_MODERATION_KEY}


def run_moderator(image_url: str, cache: bool) -> dict[str, Any]:
    url = str(
        furl(settings.AZURE_IMAGE_MODERATION_ENDPOINT)
        / "contentmoderator/moderate/v1.0/ProcessImage/Evaluate"
    )
    r = requests.post(
        url,
        params={"CacheImage": f"{str(cache).lower()}"},
        headers=get_auth_headers(),
        json={"DataRepresentation": "URL", "Value": image_url},
    )
    r.raise_for_status()
    return r.json()


def is_image_nsfw(image_url: str, cache: bool = False) -> bool:
    response = run_moderator(image_url=image_url, cache=cache)
    return response["IsImageAdultClassified"]
