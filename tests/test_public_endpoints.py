import pytest
from starlette.routing import Route
from starlette.testclient import TestClient

from bots.models import PublishedRun, Workflow
from daras_ai_v2.all_pages import all_api_pages, all_hidden_pages
from daras_ai_v2.tabs_widget import MenuTabs
from routers import facebook_api
from routers.slack_api import slack_connect_redirect_shortcuts, slack_connect_redirect
from server import app

client = TestClient(app)

excluded_endpoints = [
    facebook_api.fb_webhook_verify.__name__,  # gives 403
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
def test_all_get(threadpool_subtest):
    for path in route_paths:
        threadpool_subtest(_test_get_path, path)


def _test_get_path(path):
    r = client.get(path, allow_redirects=False)
    assert r.ok


@pytest.mark.django_db
def test_all_slugs(threadpool_subtest):
    for page_cls in all_api_pages + all_hidden_pages:
        for slug in page_cls.slug_versions:
            for tab in MenuTabs.paths.values():
                url = f"/{slug}/{tab}"
                threadpool_subtest(_test_post_path, url)


@pytest.mark.django_db
def test_all_examples(threadpool_subtest):
    qs = PublishedRun.objects.exclude(
        is_approved_example=False, published_run_id=""
    ).order_by("workflow")
    for pr in qs:
        slug = Workflow(pr.workflow).page_cls.slug_versions[-1]
        url = f"/{slug}?example_id={pr.published_run_id}"
        threadpool_subtest(_test_post_path, url)


def _test_post_path(url):
    r = client.post(url, json={}, allow_redirects=True)
    assert r.status_code == 200
