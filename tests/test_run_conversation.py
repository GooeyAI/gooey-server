import pytest

from app_users.models import AppUser
from bots.models import RunConversation, SavedRun, Workflow
from workspaces.models import Workspace


@pytest.fixture
def test_user(transactional_db):
    return AppUser.objects.create(
        uid="owner_uid", email="owner@example.com", is_anonymous=False
    )


@pytest.fixture
def test_workspace(transactional_db, test_user):
    return Workspace.objects.create(created_by=test_user, is_personal=True)


def _make_run(
    *,
    workspace,
    uid,
    run_id,
    workflow=Workflow.VIDEO_BOTS,
    surface=SavedRun.Surface.run,
):
    return SavedRun.objects.create(
        run_id=run_id,
        uid=uid,
        workspace=workspace,
        workflow=workflow,
        surface=surface,
    )


def _attach(sr, *, parent_sr, surface=SavedRun.Surface.run, title=""):
    return RunConversation.attach_run(
        sr=sr,
        parent_sr=parent_sr,
        is_continuation=parent_sr is not None,
        surface=surface,
        title=title,
    )


def test_attach_run_starts_new_conversation(test_workspace, test_user):
    sr = _make_run(workspace=test_workspace, uid=test_user.uid, run_id="r1")
    convo = _attach(sr, parent_sr=None, title="hello")

    assert RunConversation.objects.count() == 1
    sr.refresh_from_db()
    assert sr.conversation_id == convo.id
    assert convo.last_run_id == sr.id
    assert convo.title == "hello"


def test_attach_run_continues_parent_when_scope_matches(test_workspace, test_user):
    parent = _make_run(workspace=test_workspace, uid=test_user.uid, run_id="p1")
    parent_convo = _attach(parent, parent_sr=None, title="thread")

    child = _make_run(workspace=test_workspace, uid=test_user.uid, run_id="c1")
    child_convo = _attach(child, parent_sr=parent)

    # Same thread reused, head advanced to the child.
    assert RunConversation.objects.count() == 1
    assert child_convo.id == parent_convo.id
    parent_convo.refresh_from_db()
    assert parent_convo.last_run_id == child.id


def test_attach_run_does_not_continue_across_user(test_workspace, test_user):
    """A turn run by a different user must not join the owner's thread."""
    parent = _make_run(workspace=test_workspace, uid=test_user.uid, run_id="p2")
    parent_convo = _attach(parent, parent_sr=None)

    # Same parent SavedRun, but the continuation is performed by another user
    # (e.g. viewing a shared-workspace run).
    other = _make_run(workspace=test_workspace, uid="other_uid", run_id="c2")
    other_convo = _attach(other, parent_sr=parent)

    assert other_convo.id != parent_convo.id
    assert other_convo.uid == "other_uid"
    assert RunConversation.objects.count() == 2


def test_attach_run_does_not_continue_across_workspace(test_workspace, test_user):
    parent = _make_run(workspace=test_workspace, uid=test_user.uid, run_id="p3")
    parent_convo = _attach(parent, parent_sr=None)

    other_workspace = Workspace.objects.create(created_by=test_user, is_personal=False)
    child = _make_run(workspace=other_workspace, uid=test_user.uid, run_id="c3")
    child_convo = _attach(child, parent_sr=parent)

    assert child_convo.id != parent_convo.id
    assert child_convo.workspace_id == other_workspace.id
    assert RunConversation.objects.count() == 2


def test_attach_run_does_not_continue_across_surface(test_workspace, test_user):
    parent = _make_run(workspace=test_workspace, uid=test_user.uid, run_id="p4")
    parent_convo = _attach(parent, parent_sr=None, surface=SavedRun.Surface.run)

    child = _make_run(
        workspace=test_workspace,
        uid=test_user.uid,
        run_id="c4",
        surface=SavedRun.Surface.builder_child,
    )
    child_convo = _attach(
        child, parent_sr=parent, surface=SavedRun.Surface.builder_child
    )

    assert child_convo.id != parent_convo.id
    assert RunConversation.objects.count() == 2


def test_attach_run_is_atomic_on_failure(test_workspace, test_user, monkeypatch):
    """A failure on the second write must roll back the first, leaving no half state.

    Uses the continuation path so the conversation already exists: sr.save()
    (the first write) succeeds, then convo.save() (the second) blows up. Without
    the transaction the run would be left pointing at a conversation whose head
    was never advanced.
    """
    parent = _make_run(workspace=test_workspace, uid=test_user.uid, run_id="p_atomic")
    parent_convo = _attach(parent, parent_sr=None, title="thread")

    child = _make_run(workspace=test_workspace, uid=test_user.uid, run_id="c_atomic")

    # Patch only after the parent conversation exists, so attach() reuses it
    # (no create()) and reaches the final convo.save().
    def boom(self, *args, **kwargs):
        raise RuntimeError("simulated failure after run is linked")

    monkeypatch.setattr(RunConversation, "save", boom)

    with pytest.raises(RuntimeError):
        _attach(child, parent_sr=parent)

    # The child's sr.save() must have rolled back: no dangling link, head unmoved.
    child.refresh_from_db()
    parent_convo.refresh_from_db()
    assert child.conversation_id is None
    assert parent_convo.last_run_id == parent.id


def test_attach_run_does_not_continue_across_workflow(test_workspace, test_user):
    parent = _make_run(workspace=test_workspace, uid=test_user.uid, run_id="p5")
    parent_convo = _attach(parent, parent_sr=None)

    child = _make_run(
        workspace=test_workspace,
        uid=test_user.uid,
        run_id="c5",
        workflow=Workflow.COMPARE_LLM,
    )
    child_convo = _attach(child, parent_sr=parent)

    assert child_convo.id != parent_convo.id
    assert RunConversation.objects.count() == 2
