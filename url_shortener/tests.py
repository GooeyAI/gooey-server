from starlette.testclient import TestClient

from daras_ai_v2.functional import map_parallel, flatmap_parallel
from server import app
from url_shortener.models import ShortenedURL

TEST_URL = "https://www.google.com"

client = TestClient(app)


def test_url_shortener(transactional_db):
    surl = ShortenedURL.objects.create(url=TEST_URL)
    short_url = surl.shortened_url()
    r = client.get(short_url, allow_redirects=False)
    assert r.is_redirect and r.headers["location"] == TEST_URL


def test_url_shortener_max_clicks(transactional_db):
    surl = ShortenedURL.objects.create(url=TEST_URL, max_clicks=5)
    short_url = surl.shortened_url()
    for _ in range(5):
        r = client.get(short_url, allow_redirects=False)
        assert r.is_redirect and r.headers["location"] == TEST_URL
    r = client.get(short_url, allow_redirects=False)
    assert r.status_code == 410


def test_url_shortener_disabled(transactional_db):
    surl = ShortenedURL.objects.create(url=TEST_URL, disabled=True)
    short_url = surl.shortened_url()
    r = client.get(short_url, allow_redirects=False)
    assert r.status_code == 410


def test_url_shortener_create_atomic(transactional_db):
    def create(_):
        return [
            ShortenedURL.objects.create(url=TEST_URL).shortened_url()
            for _ in range(100)
        ]

    assert len(set(flatmap_parallel(create, range(5)))) == 500


def test_url_shortener_clicks_decrement_atomic(transactional_db):
    surl = ShortenedURL.objects.create(url=TEST_URL, enable_analytics=False)
    short_url = surl.shortened_url()

    def make_clicks(_):
        for _ in range(100):
            r = client.get(short_url, allow_redirects=False)
            assert r.is_redirect and r.headers["location"] == TEST_URL

    map_parallel(make_clicks, range(5))

    assert ShortenedURL.objects.get(pk=surl.pk).clicks == 500
