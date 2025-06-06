import typing

from starlette.testclient import TestClient

from bots.models import Workflow, PublishedRun
from daras_ai_v2.all_pages import all_test_pages
from daras_ai_v2.base import BasePage
from server import app

MAX_WORKERS = 20

client = TestClient(app)


def test_apis_sync(
    mock_celery_tasks, db_fixtures, force_authentication, threadpool_subtest
):
    for page_cls in all_test_pages:
        endpoint = f"/v2/{page_cls.slug_versions[0]}/"
        threadpool_subtest(_test_api_sync, page_cls, endpoint, msg=endpoint)


def _test_api_sync(page_cls: typing.Type[BasePage], endpoint: str):
    state = page_cls.get_root_pr().saved_run.state
    r = client.post(
        endpoint,
        json=page_cls.get_example_request(state)[1],
        headers={"Authorization": "Token None"},
        follow_redirects=False,
    )
    assert r.status_code == 200, r.text


def test_apis_async(
    mock_celery_tasks, db_fixtures, force_authentication, threadpool_subtest
):
    for page_cls in all_test_pages:
        endpoint = f"/v3/{page_cls.slug_versions[0]}/async/"
        threadpool_subtest(_test_api_async, page_cls, endpoint, msg=endpoint)


def _test_api_async(page_cls: typing.Type[BasePage], endpoint: str):
    state = page_cls.get_root_pr().saved_run.state

    r = client.post(
        endpoint,
        json=page_cls.get_example_request(state)[1],
        headers={"Authorization": "Token None"},
        follow_redirects=False,
    )
    assert r.status_code == 202, r.text

    status_url = r.json()["status_url"]

    r = client.get(
        status_url,
        headers={"Authorization": "Token None"},
        follow_redirects=False,
    )
    assert r.status_code == 200, r.text

    data = r.json()
    status = data.get("status")
    assert status, data
    if status == "completed":
        assert "output" in data, data


def test_apis_examples(
    mock_celery_tasks, db_fixtures, force_authentication, threadpool_subtest
):
    qs = PublishedRun.objects.filter(PublishedRun.approved_example_q())
    for pr in qs:
        page_cls = Workflow(pr.workflow).page_cls
        endpoint = f"/v2/{page_cls.slug_versions[0]}/?example_id={pr.published_run_id}"
        body = page_cls.get_example_request(pr.saved_run.state)[1]
        threadpool_subtest(_test_apis_examples, endpoint, body, msg=endpoint)


def _test_apis_examples(endpoint: str, body: dict):
    r = client.post(
        endpoint,
        json=body,
        headers={"Authorization": "Token None"},
        follow_redirects=False,
    )
    assert r.status_code == 200, r.text


def test_get_balance(transactional_db, force_authentication):
    r = client.get(
        "/v1/balance/",
        headers={"Authorization": "Token None"},
        follow_redirects=False,
    )
    assert r.status_code == 200, r.text
