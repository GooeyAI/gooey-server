import json

from furl import furl
from starlette.testclient import TestClient

from bots.models import BotIntegration, Workflow, Platform, SavedRun
from server import app

client = TestClient(app)


def test_send_msg_streaming(transactional_db, mock_celery_tasks, force_authentication):
    bi = BotIntegration.objects.create(
        platform=Platform.WEB,
        billing_account_uid=force_authentication.uid,
        saved_run=SavedRun.objects.create(
            workflow=Workflow.VIDEO_BOTS,
            uid=force_authentication.uid,
        ),
    )
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
