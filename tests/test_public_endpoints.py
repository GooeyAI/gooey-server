from starlette.routing import Route
from starlette.testclient import TestClient

from bots.models import PublishedRun, Workflow
from daras_ai_v2.all_pages import all_api_pages, all_hidden_pages
from routers import facebook_api
from routers.root import RecipeTabs
from routers.slack_api import slack_connect_redirect_shortcuts, slack_connect_redirect
from routers.static_pages import webflow_upload
from server import app

client = TestClient(app)

excluded_endpoints = [
    facebook_api.fb_webhook_verify.__name__,  # gives 403
    slack_connect_redirect.__name__,
    slack_connect_redirect_shortcuts.__name__,
    "get_run_status",  # needs query params
    "get_balance",  # needs authentication
    webflow_upload.__name__,  # needs admin authentication
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


def test_all_get(db_fixtures, threadpool_subtest):
    for path in route_paths:
        threadpool_subtest(_test_get_path, path)


def _test_get_path(path):
    r = client.get(path, allow_redirects=False)
    assert r.ok, r.content


def test_all_post(db_fixtures, force_authentication, threadpool_subtest):
    for page_cls in all_api_pages + all_hidden_pages:
        for slug in page_cls.slug_versions:
            for tab in RecipeTabs:
                threadpool_subtest(_test_post_path, tab.url_path(slug))

    published_examples = (
        PublishedRun.objects.exclude(is_approved_example=False)
        .exclude(published_run_id="")
        .order_by("workflow")
    )
    for pr in published_examples:
        slug = Workflow(pr.workflow).page_cls.slug_versions[-1]
        threadpool_subtest(
            _test_post_path,
            RecipeTabs.run.url_path(slug, "test-run-slug", pr.published_run_id),
        )


def _test_post_path(url):
    for _ in range(10):
        r = client.post(url, json={}, allow_redirects=False)
        if r.is_redirect:
            url = r.headers["Location"]
            continue
        assert r.ok, r.content
        return
    else:
        assert False, f"Too many redirects: {url}"
