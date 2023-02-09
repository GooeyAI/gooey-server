import pytest
from furl import furl
from starlette.routing import Route
from starlette.testclient import TestClient

from daras_ai_v2.settings import APP_BASE_URL
from routers import realtime, facebook
from server import app
from tests import test_apis

client = TestClient(app)

excluded_endpoints = [
    facebook.fb_webhook_verify,  # gives 403
    realtime.key_events,
]

route_paths = [
    route.path
    for route in app.routes
    if (
        isinstance(route, Route)
        and "GET" in route.methods
        and not route.param_convertors
        and route.endpoint not in excluded_endpoints
    )
] + [slug for page_cls in test_apis.pages_to_test for slug in page_cls.slug_versions]


@pytest.mark.parametrize("path", route_paths)
def test_public_endpoints(path):
    url = furl(APP_BASE_URL).add(path=path).url
    r = client.get(url, allow_redirects=True)
    print(r.content)
    assert r.status_code == 200
