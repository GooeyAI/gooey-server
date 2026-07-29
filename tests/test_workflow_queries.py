import uuid
from datetime import timedelta

from django.utils import timezone

from bots.models import PublishedRun, SavedRun, Workflow
from bots.models.message_thread import MessageThread
from widgets.workflow_queries import recent_run_ids


def test_recent_run_ids_deduplicates_published_workflows(
    transactional_db, force_authentication
):
    user = force_authentication
    workspace = user.get_or_create_personal_workspace()[0]
    first_pr = _make_published_run(user, workspace)
    second_pr = _make_published_run(user, workspace)
    second_pr_run = _make_sr(
        uid=user.uid,
        workspace=workspace,
        parent_version=second_pr.versions.first(),
    )
    _make_sr(
        uid=user.uid,
        workspace=workspace,
        parent_version=first_pr.versions.first(),
    )
    latest_first_pr_run = _make_sr(
        uid=user.uid,
        workspace=workspace,
        parent_version=first_pr.versions.first(),
    )
    now = timezone.now()
    SavedRun.objects.filter(id=second_pr_run.id).update(
        updated_at=now - timedelta(minutes=2)
    )
    SavedRun.objects.filter(id=latest_first_pr_run.id).update(updated_at=now)

    ids = recent_run_ids(
        user,
        workspace,
        limit=2,
        include_builder_runs=False,
    )

    assert ids == [latest_first_pr_run.id, second_pr_run.id]


def test_recent_run_ids_optionally_includes_builder_runs(
    transactional_db, force_authentication
):
    user = force_authentication
    workspace = user.get_or_create_personal_workspace()[0]
    published_run = _make_published_run(user, workspace)
    history_run = _make_sr(
        uid=user.uid,
        workspace=workspace,
        parent_version=published_run.versions.first(),
    )
    thread = MessageThread.objects.create(title="Build a workflow")
    builder_prompt = _make_sr(
        uid=user.uid,
        workspace=workspace,
        surface=SavedRun.Surface.builder_prompt,
        message_thread=thread,
    )
    thread.last_run = builder_prompt
    thread.save(update_fields=["last_run"])
    builder_run = _make_sr(
        uid=user.uid,
        workspace=workspace,
        surface=SavedRun.Surface.builder_child,
        parent_builder_saved_run=builder_prompt,
    )
    now = timezone.now()
    SavedRun.objects.filter(id=history_run.id).update(
        updated_at=now - timedelta(minutes=1)
    )
    SavedRun.objects.filter(id=builder_run.id).update(updated_at=now)

    home_ids = recent_run_ids(
        user,
        workspace,
        limit=2,
        include_builder_runs=False,
    )
    navigation_ids = recent_run_ids(
        user,
        workspace,
        limit=2,
        include_builder_runs=True,
    )

    assert home_ids == [history_run.id]
    assert navigation_ids == [builder_run.id, history_run.id]


def _make_published_run(user, workspace) -> PublishedRun:
    root_sr = _make_sr(
        uid=user.uid,
        workspace=workspace,
        surface=SavedRun.Surface.internal,
    )
    return PublishedRun.objects.create_with_version(
        workflow=Workflow.VIDEO_BOTS,
        published_run_id=uuid.uuid4().hex[:12],
        saved_run=root_sr,
        user=user,
        workspace=workspace,
        title="Test workflow",
    )


def _make_sr(**kwargs) -> SavedRun:
    kwargs.setdefault("workflow", Workflow.VIDEO_BOTS)
    kwargs.setdefault("run_id", uuid.uuid4().hex)
    return SavedRun.objects.create(**kwargs)
