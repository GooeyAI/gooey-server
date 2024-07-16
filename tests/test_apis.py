import typing

import pytest
from starlette.testclient import TestClient

from auth.auth_backend import force_authentication
from bots.models import Workflow, PublishedRun
from daras_ai_v2.all_pages import all_test_pages
from daras_ai_v2.base import BasePage
from server import app

MAX_WORKERS = 20

client = TestClient(app)


@pytest.mark.django_db
def test_apis_sync(mock_celery_tasks, force_authentication, threadpool_subtest):
    for page_cls in all_test_pages:
        threadpool_subtest(_test_api_sync, page_cls)


def _test_api_sync(page_cls: typing.Type[BasePage]):
    state = page_cls.recipe_doc_sr().state
    r = client.post(
        f"/v2/{page_cls.slug_versions[0]}/",
        json=page_cls.get_example_request(state)[1],
        headers={"Authorization": f"Token None"},
        allow_redirects=False,
    )
    assert r.status_code == 200, r.text


@pytest.mark.django_db
def test_apis_async(mock_celery_tasks, force_authentication, threadpool_subtest):
    for page_cls in all_test_pages:
        threadpool_subtest(_test_api_async, page_cls)


def _test_api_async(page_cls: typing.Type[BasePage]):
    state = page_cls.recipe_doc_sr().state

    r = client.post(
        f"/v3/{page_cls.slug_versions[0]}/async/",
        json=page_cls.get_example_request(state)[1],
        headers={"Authorization": f"Token None"},
        allow_redirects=False,
    )
    assert r.status_code == 202, r.text

    status_url = r.json()["status_url"]

    r = client.get(
        status_url,
        headers={"Authorization": f"Token None"},
        allow_redirects=False,
    )
    assert r.status_code == 200, r.text

    data = r.json()
    status = data.get("status")
    assert status, data
    if status == "completed":
        assert "output" in data, data


@pytest.mark.django_db
def test_apis_examples(mock_celery_tasks, force_authentication, threadpool_subtest):
    qs = (
        PublishedRun.objects.exclude(is_approved_example=False)
        .exclude(published_run_id="")
        .order_by("workflow")
    )
    for pr in qs:
        page_cls = Workflow(pr.workflow).page_cls
        endpoint = f"/v2/{page_cls.slug_versions[0]}/?example_id={pr.published_run_id}"
        body = page_cls.get_example_request(pr.saved_run.state)[1]
        threadpool_subtest(_test_apis_examples, endpoint, body, msg=endpoint)


def _test_apis_examples(endpoint: str, body: dict):
    r = client.post(
        endpoint,
        json=body,
        headers={"Authorization": f"Token None"},
        allow_redirects=False,
    )
    assert r.status_code == 200, r.text


@pytest.mark.django_db
def test_get_balance(force_authentication):
    r = client.get(
        "/v1/balance/",
        headers={"Authorization": "Token None"},
        allow_redirects=False,
    )
    assert r.status_code == 200, r.text
