"""
Tests that all API pages can be called without any AI model API keys configured.
This ensures pages don't hard-depend on third-party credentials just to handle
a request (schema generation, request validation, dispatching the task, etc.).
The actual model execution is mocked via mock_celery_tasks.
"""

import os
import typing
from contextlib import ExitStack
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from daras_ai_v2.all_pages import all_test_pages
from daras_ai_v2.base import BasePage
from server import app

client = TestClient(app)

# Mapping of settings attribute name → os.environ key (None if not in os.environ).
# REPLICATE_API_TOKEN is only set into os.environ directly in settings.py (no module attr).
_SETTINGS_ATTRS = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "FAL_API_KEY",
    "GROQ_API_KEY",
    "FIREWORKS_API_KEY",
    "MISTRAL_API_KEY",
    "HF_TOKEN",
    "SARVAM_API_KEY",
    "DEEPGRAM_API_KEY",
    "ELEVEN_LABS_API_KEY",
    "REPLICATE_API_KEY",
]

# Keys that are only injected into os.environ (no settings module attribute).
_ENV_ONLY_KEYS = [
    "REPLICATE_API_TOKEN",
]

# Keys written into os.environ by settings.py that should also be blanked there.
_SETTINGS_AND_ENV_KEYS = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
]


def no_ai_keys():
    """Context manager that blanks every AI model API key."""
    stack = ExitStack()
    for attr in _SETTINGS_ATTRS:
        stack.enter_context(patch(f"daras_ai_v2.settings.{attr}", ""))
    for key in _ENV_ONLY_KEYS + _SETTINGS_AND_ENV_KEYS:
        stack.enter_context(patch.dict(os.environ, {key: ""}))
    return stack


def test_apis_sync_without_keys(
    mock_celery_tasks, db_fixtures, force_authentication, threadpool_subtest
):
    for page_cls in all_test_pages:
        endpoint = f"/v2/{page_cls.slug_versions[0]}/"
        threadpool_subtest(
            _test_api_sync_without_keys, page_cls, endpoint, msg=endpoint
        )


def _test_api_sync_without_keys(page_cls: typing.Type[BasePage], endpoint: str):
    with no_ai_keys():
        state = page_cls.get_root_pr().saved_run.state
        r = client.post(
            endpoint,
            json=page_cls.get_example_request(state)[1],
            headers={"Authorization": "Token None"},
            follow_redirects=False,
        )
        assert r.status_code == 200, r.text


def test_apis_async_without_keys(
    mock_celery_tasks, db_fixtures, force_authentication, threadpool_subtest
):
    for page_cls in all_test_pages:
        endpoint = f"/v3/{page_cls.slug_versions[0]}/async/"
        threadpool_subtest(
            _test_api_async_without_keys, page_cls, endpoint, msg=endpoint
        )


def _test_api_async_without_keys(page_cls: typing.Type[BasePage], endpoint: str):
    with no_ai_keys():
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


def no_google_credentials():
    """Context manager that removes the Google service account from the environment."""
    return patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": ""})


def test_google_tts_without_credentials(transactional_db):
    from google.api_core.exceptions import GoogleAPICallError
    from google.auth.exceptions import DefaultCredentialsError

    from daras_ai_v2.text_to_speech_settings_widgets import TextToSpeechProviders
    from recipes.TextToSpeech import TextToSpeechPage

    state = {
        "text_prompt": "Hello, world.",
        "tts_provider": TextToSpeechProviders.GOOGLE_TTS.name,
        "google_voice_name": "en-US-Neural2-F",
    }

    page = TextToSpeechPage()

    with no_google_credentials():
        with pytest.raises(
            (GoogleAPICallError, DefaultCredentialsError, Exception)
        ) as exc_info:
            for _ in page.run(state):
                pass

    # Confirm the failure is credential-related, not an unexpected crash
    err = str(exc_info.value).lower()
    assert any(
        kw in err
        for kw in (
            "credential",
            "authentication",
            "permission",
            "unauthenticated",
            "403",
            "401",
        )
    ), f"Expected a credentials error, got: {exc_info.value}"
