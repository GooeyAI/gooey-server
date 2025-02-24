import json

from furl import furl
from starlette.testclient import TestClient

from bots.models import BotIntegration, Platform
from server import app

client = TestClient(app)


def test_send_msg_streaming(db_fixtures, force_authentication, mock_celery_tasks):
    bi = BotIntegration.objects.filter(platform=Platform.WEB).first()
    r = client.post(
        "/v3/integrations/stream/",
        json={
            "integration_id": bi.api_integration_id(),
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
        if event.startswith("event: close"):
            actual_events.append("close")
            continue
        assert not event.startswith("event: error"), event
        data = event.removeprefix("data: ")
        if not data:
            continue
        event = json.loads(data)
        actual_events.append(event["type"])

    expected_events = [
        "conversation_start",
        "run_start",
        "message_part",
        "final_response",
        "close",
    ]

    assert actual_events == expected_events
