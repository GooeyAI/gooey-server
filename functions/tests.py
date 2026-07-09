from types import SimpleNamespace

import azure.core.exceptions
import pytest

from app_users.models import AppUser
from daras_ai_v2 import settings
from daras_ai_v2.language_model_openai_realtime import yield_from
from functions.models import FunctionScopes
from managed_secrets.models import ManagedSecret
from memory.models import MemoryEntry
from recipes.Functions import FunctionsPage, CodeLanguages

pytestmark = [
    pytest.mark.skipif(
        not settings.CF_FUNCTIONS_URL, reason="CF_FUNCTIONS_URL is not set"
    ),
    pytest.mark.django_db,
]


def test_js_lodash():
    request = FunctionsPage.RequestModel(
        code="""
        import _ from 'lodash';

        async () => {
            const users = [
                { name: 'barney', age: 36 },
                { name: 'fred', age: 40 },
                { name: 'pebbles', age: 1 },
            ];
            return _.map(_.sortBy(users, 'age'), 'name').join(',');
        };
        """,
        language=CodeLanguages.javascript.name,
        package_json={
            "dependencies": {"lodash": "^4.17.21"},
        },
    )
    response = FunctionsPage.ResponseModel()
    user = AppUser.objects.create(is_anonymous=False, balance=1000)
    yield_from(FunctionsPage(user=user).run_v2(request, response))
    assert response.return_value == "pebbles,barney,fred"


def test_js_error():
    request = FunctionsPage.RequestModel(
        code="""
        import _ from 'foobar';
        """,
        language=CodeLanguages.javascript.name,
        package_json={},
    )
    response = FunctionsPage.ResponseModel()
    user = AppUser.objects.create(is_anonymous=False, balance=1000)
    yield_from(FunctionsPage(user=user).run_v2(request, response))
    assert 'No such module "src/foobar"' in response.error


def test_js_variables():
    request = FunctionsPage.RequestModel(
        code="""
        async ({ myvar }) => myvar;
        """,
        language=CodeLanguages.javascript.name,
        package_json={},
        variables={"myvar": "test_value"},
    )
    response = FunctionsPage.ResponseModel()
    user = AppUser.objects.create(is_anonymous=False, balance=1000)
    yield_from(FunctionsPage(user=user).run_v2(request, response))
    assert response.return_value == "test_value"


@pytest.mark.django_db(transaction=True)
def test_js_secrets(mock_az_secrets):
    user = AppUser.objects.create(is_anonymous=False, balance=1000)
    workspace = user.get_or_create_personal_workspace()[0]
    secret = ManagedSecret.objects.create(
        workspace=workspace, created_by=user, name="TEST_VAR", value="test_value"
    )
    secret.value = "test_value"
    request = FunctionsPage.RequestModel(
        code="""
        process.env.TEST_VAR;
        """,
        language=CodeLanguages.javascript.name,
        package_json={},
        secrets=[secret.name],
    )
    response = FunctionsPage.ResponseModel()
    yield_from(FunctionsPage(user=user).run_v2(request, response))
    assert response.return_value == secret.value


@pytest.fixture
def mock_az_secrets(monkeypatch):
    store = {}

    class MockSecretClient:
        def set_secret(self, name, value):
            store[name] = value

        def get_secret(self, name):
            try:
                return SimpleNamespace(value=store[name])
            except KeyError:
                raise azure.core.exceptions.ResourceNotFoundError()

        def begin_delete_secret(self, name):
            store.pop(name, None)

    monkeypatch.setattr(
        "managed_secrets.models._get_az_secret_client", MockSecretClient
    )


def test_js_expression():
    request = FunctionsPage.RequestModel(
        code="40 + 2",
        language=CodeLanguages.javascript.name,
    )
    response = FunctionsPage.ResponseModel()
    user = AppUser.objects.create(is_anonymous=False, balance=1000)
    yield_from(FunctionsPage(user=user).run_v2(request, response))
    assert response.return_value == 42


def test_js_helper_functions():
    request = FunctionsPage.RequestModel(
        code="""
        async ({ name }) => {
            console.log("running for", name);
            await square(4);
            return `Hello, ${name}!`;
        }
        const square = async (number) => {
          return number * number;
        };
        """,
        language=CodeLanguages.javascript.name,
        variables={"name": "Gooey"},
    )
    response = FunctionsPage.ResponseModel()
    user = AppUser.objects.create(is_anonymous=False, balance=1000)
    yield_from(FunctionsPage(user=user).run_v2(request, response))
    assert response.return_value == "Hello, Gooey!"
    assert response.logs == [{"level": "log", "message": "running for Gooey"}]


def test_gooey_memory():
    request = FunctionsPage.RequestModel(
        code="GOOEY_MEMORY.x = 42",
        language=CodeLanguages.javascript.name,
        memory_scope=FunctionScopes.workspace.name,
    )
    response = FunctionsPage.ResponseModel()
    user = AppUser.objects.create(is_anonymous=False, balance=1000)
    yield_from(FunctionsPage(user=user).run_v2(request, response))
    assert MemoryEntry.objects.get(key="x").value == 42
