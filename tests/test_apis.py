import typing

import pytest
from fastapi.testclient import TestClient

from daras_ai_v2.base import (
    BasePage,
    get_example_request_body,
    get_saved_doc_nocahe,
    get_doc_ref,
)
from server import app, all_pages

client = TestClient(app)


@pytest.mark.parametrize("page_cls", all_pages)
def test_apis_basic(page_cls: typing.Type[BasePage]):
    page = page_cls()
    state = get_saved_doc_nocahe(get_doc_ref(page.doc_name))

    r = client.post(
        page.endpoint,
        json=get_example_request_body(page.RequestModel, state),
    )

    assert r.ok, r.content
