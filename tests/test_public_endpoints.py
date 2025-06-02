import random

from starlette.routing import Route
from starlette.testclient import TestClient

from bots.models import (
    CHATML_ROLE_ASSISTANT,
    CHATML_ROLE_USER,
    BotIntegration,
    Conversation,
    Message,
    PublishedRun,
    Workflow,
)
from daras_ai_v2.fastapi_tricks import get_route_path
from routers import facebook_api
from routers.root import RecipeTabs, integrations_stats_route
from routers.slack_api import slack_connect_redirect, slack_connect_redirect_shortcuts
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
    r = client.get(path, follow_redirects=False)
    assert r.is_success, r.content


def test_integration_stats_route(db_fixtures, force_authentication, threadpool_subtest):
    for bi in BotIntegration.objects.all():
        for i in range(5):
            convo = Conversation.objects.create(
                bot_integration=bi, web_user_id=f"test-user-id-{i % 2}"
            )
            for j in range(10):
                Message.objects.create(
                    conversation=convo,
                    role=CHATML_ROLE_USER,
                    content="test-message-1",
                )
                Message.objects.create(
                    conversation=convo,
                    role=CHATML_ROLE_ASSISTANT,
                    content="test-message-2",
                )
        url_path = get_route_path(
            integrations_stats_route,
            path_params=dict(
                page_slug="test-slug",
                integration_id=bi.api_integration_id(),
            ),
        )
        threadpool_subtest(
            _test_post_path,
            url_path,
            "2 Active Users",
            "5 Conversations",
            "100 Total Messages",
        )


def test_all_post(db_fixtures, force_authentication, threadpool_subtest):
    for pr in PublishedRun.objects.all():
        for tab in RecipeTabs:
            slug = random.choice(Workflow(pr.workflow).page_cls.slug_versions)
            url_path = tab.url_path(slug, "test-run-slug", pr.published_run_id)
            if RecipeTabs in [RecipeTabs.run, RecipeTabs.run_as_api]:
                test_content = [pr.title]
            else:
                test_content = []
            threadpool_subtest(_test_post_path, url_path, *test_content)


def _test_post_path(url, *test_content):
    for _ in range(10):
        r = client.post(url, json={}, follow_redirects=False)
        if r.is_redirect:
            url = r.headers["Location"]
            continue
        assert r.is_success, r.content
        for expected in test_content:
            assert expected in str(r.json()), str(r.json())
        return
    else:
        assert False, f"Too many redirects: {url}"
