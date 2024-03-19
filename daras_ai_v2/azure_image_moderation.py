import requests
from furl import furl

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status


def get_auth_headers():
    return {"Ocp-Apim-Subscription-Key": settings.AZURE_IMAGE_MODERATION_KEY}


def is_image_nsfw(image_url: str, cache: bool = False) -> bool:
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
    if r.status_code == 400 and (
        b"Image Size Error" in r.content or b"Image Error" in r.content
    ):
        return False
    raise_for_status(r)
    return r.json().get("IsImageAdultClassified", False)
