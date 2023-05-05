import typing

import pytest
from fastapi.testclient import TestClient

from auth_backend import force_authentication
from daras_ai_v2 import db
from daras_ai_v2.all_pages import all_test_pages
from daras_ai_v2.base import (
    BasePage,
    get_example_request_body,
)
from server import app

client = TestClient(app)


@pytest.mark.parametrize("page_cls", all_test_pages)
def test_apis_basic(page_cls: typing.Type[BasePage], test_auth_user):
    page = page_cls()
    state = db.get_or_create_doc(db.get_doc_ref(page.doc_name)).to_dict()

    with force_authentication(test_auth_user):
        r = client.post(
            page.endpoint,
            json=get_example_request_body(page.RequestModel, state),
            headers={"Authorization": f"Token None"},
        )

    print(r.content)
    assert r.ok
