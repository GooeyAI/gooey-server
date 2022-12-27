import pytest
from decouple import config
from firebase_admin import auth

from gooey_token_authentication1.token_authentication import authenticate_credentials


@pytest.fixture
def test_auth_user() -> auth.UserRecord:
    return authenticate_credentials(config("TEST_RUNNER_API_KEY"))
