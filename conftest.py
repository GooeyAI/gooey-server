import pytest
from decouple import config
from firebase_admin import auth

from daras_ai_v2 import db
from gooey_token_authentication1.token_authentication import authenticate_credentials


@pytest.fixture(scope="session")
def test_auth_user() -> auth.UserRecord:
    email = config("TEST_RUNNER_EMAIL")
    api_key = config("TEST_RUNNER_API_KEY")

    # get test runner user
    try:
        user = auth.get_user_by_email(email)
    except auth.UserNotFoundError:
        user = auth.create_user(email=email)

    # ensure user has credits
    doc_ref = db.get_user_doc_ref(user.uid)
    doc_ref.set({db.USER_BALANCE_FIELD: 1000}, merge=True)

    # authenticate via api key
    return authenticate_credentials(api_key)
