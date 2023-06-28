import os.path

import pytest
from starlette.routing import Route
from starlette.testclient import TestClient

from auth_backend import force_authentication
from daras_ai_v2.all_pages import all_api_pages
from daras_ai_v2.tabs_widget import MenuTabs
from routers import facebook
from server import app

client = TestClient(app)

excluded_endpoints = [
    facebook.fb_webhook_verify,  # gives 403
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
]


@pytest.mark.parametrize("path", route_paths)
def test_all_get(path):
    r = client.get(path, allow_redirects=False)
    print(r.content)
    assert r.ok


page_slugs = [slug for page_cls in all_api_pages for slug in page_cls.slug_versions]
tabs = list(MenuTabs.paths.values())


@pytest.mark.parametrize("tab", tabs)
@pytest.mark.parametrize("slug", page_slugs)
def test_page_slugs(slug, tab):
    with force_authentication():
        r = client.post(os.path.join(slug, tab), json={}, allow_redirects=True)
    print(r.content)
    assert r.status_code == 200
