import typing

import pytest
from starlette.testclient import TestClient

from auth.auth_backend import force_authentication
from bots.models import SavedRun, Workflow
from daras_ai_v2.all_pages import all_test_pages
from daras_ai_v2.base import BasePage
from server import app

MAX_WORKERS = 20

client = TestClient(app)


@pytest.mark.django_db
def test_apis_sync(mock_gui_runner, force_authentication, threadpool_subtest):
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
def test_apis_async(mock_gui_runner, force_authentication, threadpool_subtest):
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
    assert data.get("status") == "completed", data
    assert data.get("output") is not None, data


@pytest.mark.django_db
def test_apis_examples(mock_gui_runner, force_authentication, threadpool_subtest):
    for page in all_test_pages:
        for sr in SavedRun.objects.filter(
            workflow=page.workflow,
            hidden=False,
            example_id__isnull=False,
        ):
            threadpool_subtest(_test_apis_examples, sr, msg=sr.get_app_url())


def _test_apis_examples(sr: SavedRun):
    state = sr.state
    page_cls = Workflow(sr.workflow).page_cls
    r = client.post(
        f"/v2/{page_cls.slug_versions[0]}/?example_id={sr.example_id}",
        json=page_cls.get_example_request(state)[1],
        headers={"Authorization": f"Token None"},
        allow_redirects=False,
    )
    assert r.status_code == 200, r.text
