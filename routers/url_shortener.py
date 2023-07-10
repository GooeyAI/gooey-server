from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from bots.models import ShortenedURLs, SavedRun, Workflow
from furl import furl
import random
import string
from daras_ai_v2.crypto import get_random_string
from django.db import transaction
from django.db.models import F
from django.db.models import Q

app = APIRouter()


@app.get("/q/{shortened_guid}")
@transaction.atomic
def redirect_via_short_url(shortened_guid):
    shortened = (
        ShortenedURLs.objects.select_for_update()  # acquire lock on the selected row (if any)
        .filter(
            Q(max_clicks__gt=F("clicks"))
            | Q(max_clicks=-1),  # max_clicks > clicks or max_clicks = -1
            shortened_guid=shortened_guid,
            disabled=False,
        )
        .first()
    )
    if not shortened:
        return HTTPException(status_code=404, detail="Shortened URL not found")
    shortened.clicks += 1
    shortened.save()
    return RedirectResponse(url=shortened.url, status_code=303)


MIN_URL_LENGTH = 3
MAX_URL_LENGTH = 6
ATTEMPTS = 10


def is_already_used(shortened_guid):
    return ShortenedURLs.objects.filter(shortened_guid=shortened_guid).exists()


def random_url_string():
    return get_random_string(
        random.randint(MIN_URL_LENGTH, MAX_URL_LENGTH),
        string.ascii_letters + string.digits,
    )


def generate_short_url():
    # TODO: smarter way to generate unique short url
    for _ in range(ATTEMPTS):
        shortened_guid = random_url_string()
        if not is_already_used(shortened_guid):
            return shortened_guid
    raise ValueError("Could not generate unique short url")


def get_or_create_short_url(
    url: str,
    run_url: str,
    workflow: Workflow,
    max_clicks: int = -1,
    disabled: bool = False,
) -> str:
    """Create a short url for the given url and add it to the database."""
    run = (
        SavedRun.objects.get_or_create(workflow=workflow, **furl(run_url).query.params)[
            0
        ]
        if run_url
        else None
    )
    shortened_guid = generate_short_url()
    shortened_url = ShortenedURLs(
        url=url,
        run=run,
        shortened_guid=shortened_guid,
        max_clicks=max_clicks,
        disabled=disabled,
    )
    shortened_url.save()
    return shortened_url.shortened_url


def get_visits(shortened_guid: str) -> int | None:
    shortened = ShortenedURLs.objects.filter(shortened_guid=shortened_guid).first()
    if not shortened:
        return None
    return shortened.clicks
