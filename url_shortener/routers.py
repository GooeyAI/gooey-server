from django.db.models import F
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.responses import Response

from url_shortener.models import ShortenedURL
from url_shortener.tasks import save_click_info

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
    if surl.enable_analytics:
        save_click_info.delay(
            surl.id, request.client.host, request.headers.get("user-agent", "")
        )
    if surl.url:
        return RedirectResponse(
            url=surl.url, status_code=303  # because youtu.be redirects are 303
        )
    elif surl.content:
        return Response(
            content=surl.content,
            media_type=surl.content_type or "text/plain",
        )
    else:
        return Response(status_code=204)
