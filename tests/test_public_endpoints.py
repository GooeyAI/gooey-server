from furl import furl
from starlette.routing import Route
from starlette.testclient import TestClient

from daras_ai_v2.settings import APP_BASE_URL
from server import app

client = TestClient(app)
excluded_routes = [
    "/__/fb/webhook/",  # gives 403
]


def test_apis_basic():
    for route in app.routes:
        if isinstance(route, Route):
            get_method_allowed = "GET" in route.methods
            not_in_excluded_routes = route.path not in excluded_routes
            if get_method_allowed and not_in_excluded_routes:
                url = furl(APP_BASE_URL).add(path=route.path).url
                r = client.get(url)
                assert r.ok, r.content
