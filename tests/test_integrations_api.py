import json

import pytest
from furl import furl
from starlette.testclient import TestClient

from bots.models import BotIntegration
from server import app

client = TestClient(app)


@pytest.mark.django_db
def test_send_msg_streaming(mock_celery_tasks, force_authentication):
    r = client.post(
        "/v3/integrations/stream/",
        json={
            "integration_id": BotIntegration.objects.first().api_integration_id(),
            "input_text": "hello, world",
        },
        allow_redirects=False,
    )
    assert r.ok, r.text

    r = client.get(
        str(furl(r.headers["Location"]).path),
        allow_redirects=False,
    )
    assert r.ok, r.text
    assert r.headers["Content-Type"].startswith("text/event-stream")

    actual_events = []
    for event in r.text.split("\n\n"):
        assert not event.startswith("event: error"), event
        data = event.split("data: ")[-1]
        if not data:
            continue
        event = json.loads(data)
        actual_events.append(event["type"])

    expected_events = [
        "conversation_start",
        "run_start",
        "message_part",
        "final_response",
    ]

    assert actual_events == expected_events
