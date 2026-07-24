import uuid

from starlette.testclient import TestClient

from app_users.models import AppUser
from bots.models import PublishedRun, SavedRun, Workflow
from bots.models.message_thread import MessageThread
from server import app

client = TestClient(app)


def test_fetch_builder_conversations_lists_only_latest_thread_run(
    transactional_db, force_authentication
):
    user = force_authentication
    workspace = user.get_or_create_personal_workspace()[0]

    thread = MessageThread.objects.create(title="build me a bot")
    old_prompt = _make_sr(
        uid=user.uid,
        workspace=workspace,
        surface=SavedRun.Surface.builder_prompt,
        message_thread=thread,
    )
    new_prompt = _make_sr(
        uid=user.uid,
        workspace=workspace,
        surface=SavedRun.Surface.builder_prompt,
        message_thread=thread,
    )
    thread.first_run = old_prompt
    thread.last_run = new_prompt
    thread.save(update_fields=["first_run", "last_run"])

    # child of a superseded prompt run - should be excluded
    _make_sr(
        uid=user.uid,
        workspace=workspace,
        surface=SavedRun.Surface.builder_child,
        parent_builder_saved_run=old_prompt,
    )
    latest_child = _make_sr(
        uid=user.uid,
        workspace=workspace,
        surface=SavedRun.Surface.builder_child,
        parent_builder_saved_run=new_prompt,
    )
    # another user's child of the same prompt run - should be excluded
    _make_sr(
        uid="someone-else",
        workspace=workspace,
        surface=SavedRun.Surface.builder_child,
        parent_builder_saved_run=new_prompt,
    )

    r = client.post(
        "/__/gooey-builder/fetch-conversations", json=dict(run_url="unused")
    )

    assert r.status_code == 200, r.text
    assert r.json() == [
        dict(
            title="build me a bot",
            timestamp=latest_child.updated_at.isoformat(),
            url=latest_child.get_app_url(),
        )
    ]


def test_fetch_chat_conversations_lists_only_latest_thread_run(
    transactional_db, force_authentication
):
    user = force_authentication
    workspace = user.get_or_create_personal_workspace()[0]
    pr = _make_published_run(user, workspace)
    version = pr.versions.first()

    thread = MessageThread.objects.create(title="hello bot")
    old_run = _make_sr(
        uid=user.uid,
        workspace=workspace,
        parent_version=version,
        message_thread=thread,
    )
    latest_run = _make_sr(
        uid=user.uid,
        workspace=workspace,
        parent_version=version,
        message_thread=thread,
    )
    thread.first_run = old_run
    thread.last_run = latest_run
    thread.save(update_fields=["first_run", "last_run"])

    # run without any thread - should be excluded
    _make_sr(uid=user.uid, workspace=workspace, parent_version=version)

    r = client.post(
        "/__/agent/fetch-conversations", json=dict(run_url=pr.get_app_url())
    )

    assert r.status_code == 200, r.text
    assert r.json() == [
        dict(
            title="hello bot",
            timestamp=latest_run.updated_at.isoformat(),
            url=latest_run.get_app_url(),
        )
    ]


def _make_published_run(user: AppUser, workspace) -> PublishedRun:
    root_sr = _make_sr(uid=user.uid, workspace=workspace)
    return PublishedRun.objects.create_with_version(
        workflow=Workflow.VIDEO_BOTS,
        published_run_id=uuid.uuid4().hex[:12],
        saved_run=root_sr,
        user=user,
        workspace=workspace,
        title="test bot",
    )


def _make_sr(**kwargs) -> SavedRun:
    kwargs.setdefault("workflow", Workflow.VIDEO_BOTS)
    kwargs.setdefault("run_id", uuid.uuid4().hex)
    return SavedRun.objects.create(**kwargs)
