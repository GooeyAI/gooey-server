from django.db.models import F
from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from fastapi.responses import Response

from url_shortener.models import ShortenedURL

app = APIRouter()


@app.api_route("/2/{hashid}", methods=["GET", "POST"])
@app.api_route("/2/{hashid}/", methods=["GET", "POST"])
def url_shortener(hashid: str):
    try:
        surl = ShortenedURL.objects.get_by_hashid(hashid)
    except ShortenedURL.DoesNotExist:
        return Response(status_code=404)
    # ensure that the url is not disabled and has not exceeded max clicks
    if surl.disabled or (surl.max_clicks and surl.clicks >= surl.max_clicks):
        return Response(status_code=410, content="This link has expired")
    # increment the click count
    ShortenedURL.objects.filter(id=surl.id).update(clicks=F("clicks") + 1)
    return RedirectResponse(
        url=surl.url, status_code=303  # because youtu.be redirects are 303
    )
