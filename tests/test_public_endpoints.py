import pytest
from starlette.routing import Route
from starlette.testclient import TestClient

from bots.models import SavedRun
from daras_ai_v2.all_pages import all_api_pages
from daras_ai_v2.tabs_widget import MenuTabs
from routers import facebook
from routers.slack import slack_connect_redirect_shortcuts, slack_connect_redirect
from server import app

client = TestClient(app)

excluded_endpoints = [
    facebook.fb_webhook_verify.__name__,  # gives 403
    slack_connect_redirect.__name__,
    slack_connect_redirect_shortcuts.__name__,
    "get_run_status",  # needs query params
]

route_paths = [
    route.path
    for route in app.routes
    if (
        isinstance(route, Route)
        and "GET" in route.methods
        and not route.param_convertors
        and route.endpoint.__name__ not in excluded_endpoints
    )
]


@pytest.mark.django_db
@pytest.mark.parametrize("path", route_paths)
def test_all_get(path):
    r = client.get(path, allow_redirects=False)
    assert r.ok


page_slugs = [slug for page_cls in all_api_pages for slug in page_cls.slug_versions]
tabs = list(MenuTabs.paths.values())


@pytest.mark.django_db
@pytest.mark.parametrize("slug", page_slugs)
@pytest.mark.parametrize("tab", tabs)
def test_page_slugs(slug, tab):
    r = client.post(
        f"/{slug}/{tab}",
        json={},
        allow_redirects=True,
    )
    assert r.status_code == 200


@pytest.mark.django_db
def test_example_slugs(subtests):
    for page_cls in all_api_pages:
        for tab in tabs:
            for example_id in SavedRun.objects.filter(
                workflow=page_cls.workflow,
                hidden=False,
                example_id__isnull=False,
            ).values_list("example_id", flat=True):
                slug = page_cls.slug_versions[0]
                url = f"/{slug}/{tab}?example_id={example_id}"
                with subtests.test(msg=url):
                    r = client.post(url, json={}, allow_redirects=True)
                    assert r.status_code == 200
