from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from bots.models import ShortenedURLs, SavedRun, Workflow
from furl import furl
import random
import string

app = APIRouter()


@app.get("/l/{shortened_guid}")
def redirect_via_short_url(shortened_guid):
    try:
        shortened = ShortenedURLs.objects.get(shortened_guid=shortened_guid)
    except ShortenedURLs.DoesNotExist:
        return "Shortened URL not found"
    if shortened.disabled:
        return "Shortened URL disabled"
    if shortened.max_clicks >= 0 and shortened.clicks >= shortened.max_clicks:
        return "Shortened URL expired"
    shortened.clicks += 1
    shortened.save()
    response = RedirectResponse(url=shortened.url)
    return response


URL_PREFIX = "https://api.gooey.ai/l/"
MIN_URL_LENGTH = 4
MAX_URL_LENGTH = 8


def is_already_used(shortened_guid):
    return ShortenedURLs.objects.filter(shortened_guid=shortened_guid).count() == 0


def random_url_string():
    return "".join(
        random.choice(string.ascii_letters + string.digits)
        for _ in range(random.randint(MIN_URL_LENGTH, MAX_URL_LENGTH))
    )


def generate_short_url():
    # TODO: smarter way to generate unique short url
    shortened_guid = random_url_string()
    while not is_already_used(shortened_guid):
        shortened_guid = random_url_string()
    return URL_PREFIX + shortened_guid, shortened_guid


def get_or_create_short_url(
    url: str,
    run_url: str,
    workflow: Workflow,
    max_clicks: int = -1,
    disabled: bool = False,
) -> str:
    """Create a short url for the given url and add it to the database."""
    try:
        return ShortenedURLs.objects.get(url=url).shortened_url
    except ShortenedURLs.DoesNotExist:
        run = (
            SavedRun.objects.get_or_create(
                workflow=workflow, **furl(run_url).query.params
            )[0]
            if run_url
            else None
        )
        shortened_url, shortened_guid = generate_short_url()
        ShortenedURLs(
            url=url,
            run=run,
            shortened_url=shortened_url,
            shortened_guid=shortened_guid,
            max_clicks=max_clicks,
            disabled=disabled,
        ).save()
        return shortened_url
