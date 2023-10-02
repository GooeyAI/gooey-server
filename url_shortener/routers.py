from django.db.models import F
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.responses import Response
import re
import requests

from url_shortener.models import ShortenedURL, ClickAnalytic

app = APIRouter()


@app.api_route("/2/{hashid}", methods=["GET", "POST"])
@app.api_route("/2/{hashid}/", methods=["GET", "POST"])
def url_shortener(hashid: str, request: Request):
    try:
        surl = ShortenedURL.objects.get_by_hashid(hashid)
    except ShortenedURL.DoesNotExist:
        return Response(status_code=404)
    # ensure that the url is not disabled and has not exceeded max clicks
    if surl.disabled or (surl.max_clicks and surl.clicks >= surl.max_clicks):
        return Response(status_code=410, content="This link has expired")
    # increment the click count
    ShortenedURL.objects.filter(id=surl.id).update(clicks=F("clicks") + 1)
    if surl.use_analytics:
        ip_address = request.client.host  # does not work for localhost or with nginx
        user_agent = request.headers.get(
            "user-agent", ""
        )  # note all user agent info can be spoofed
        platform = getPlatform(user_agent)
        operating_system = getOperatingSystem(user_agent)
        device_model = getAndroidDeviceModel(user_agent)
        res = requests.get(f"https://iplist.cc/api/{ip_address}")
        location_data = res.json() if res.ok else {}
        # not all location data will always be available
        country_name = location_data.get("countryname", "")
        city_name = location_data.get("city", "")
        ClickAnalytic.objects.create(
            shortened_url=surl,
            ip_address=ip_address,
            user_agent=user_agent,
            platform=platform,
            operating_system=operating_system,
            device_model=device_model,
            location_data=location_data,
            country_name=country_name,
            city_name=city_name,
        )
    return RedirectResponse(
        url=surl.url, status_code=303  # because youtu.be redirects are 303
    )


def getPlatform(user_agent: str):
    devices = [
        "Android",
        "webOS",
        "iPhone",
        "iPad",
        "iPod",
        "BlackBerry",
        "IEMobile",
        "Opera Mini",
    ]
    return "mobile" if any(device in user_agent for device in devices) else "desktop"


def getOperatingSystem(user_agent: str):
    if "Win" in user_agent:
        return "Windows"
    elif "Mac" in user_agent:
        return "MacOS"
    elif "Linux" in user_agent:
        return "Linux"
    elif "Android" in user_agent:
        return "Android"
    elif "like Mac" in user_agent:
        return "iOS"
    else:
        return "Other"


def getAndroidDeviceModel(user_agent: str):
    regex = r"Android (\d+(?:\.\d+)*);"
    matches = re.search(regex, user_agent)
    if matches:
        return matches.group(1)
    else:
        return "Other"
