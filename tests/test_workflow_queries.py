import uuid
from datetime import timedelta
from types import SimpleNamespace

from django.utils import timezone

from app_users.models import AppUser
from bots.models import PublishedRun, SavedRun, Workflow
from bots.models.message_thread import MessageThread
from bots.models.bot_integration import BotIntegration, Platform
from bots.models.convo_msg import Conversation
from bots.models.workflow import WorkflowMetadata
from widgets.workflow_cards import author_from_user, history_card
from widgets.workflow_queries import USAGE_SURFACES, recent_run_ids, usage_runs


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


def test_recent_run_ids_includes_childless_builder_conversations(
    transactional_db, force_authentication
):
    user = force_authentication
    workspace = user.get_or_create_personal_workspace()[0]
    # a standalone /new/ conversation: the builder_prompt is its thread head and
    # never produced a workflow child, so it isn't covered by the history or
    # builder_child queries.
    thread = MessageThread.objects.create(title="Which AI models understand Hausa?")
    builder_prompt = _make_sr(
        uid=user.uid,
        workspace=workspace,
        surface=SavedRun.Surface.builder_prompt,
        message_thread=thread,
    )
    thread.last_run = builder_prompt
    thread.save(update_fields=["last_run"])

    home_ids = recent_run_ids(
        user,
        workspace,
        limit=5,
        include_builder_runs=False,
    )
    navigation_ids = recent_run_ids(
        user,
        workspace,
        limit=5,
        include_builder_runs=True,
    )

    # absent from the home page, surfaced in the navigation sidebar
    assert home_ids == []
    assert navigation_ids == [builder_prompt.id]


def test_usage_is_scoped_to_one_app_not_the_whole_recipe(
    transactional_db, force_authentication
):
    # two copilots in one workspace share a workflow, so the surface alone can't
    # tell their deployed chats apart
    user = force_authentication
    workspace = user.get_or_create_personal_workspace()[0]
    this_app = _make_published_run(user, workspace)
    other_app = _make_published_run(user, workspace)
    mine = _make_sr(
        uid=user.uid,
        workspace=workspace,
        surface=SavedRun.Surface.deployment,
        parent_version=this_app.versions.first(),
    )
    _make_sr(
        uid=user.uid,
        workspace=workspace,
        surface=SavedRun.Surface.deployment,
        parent_version=other_app.versions.first(),
    )

    runs = usage_runs(
        workflow=Workflow.VIDEO_BOTS,
        workspace=workspace,
        published_run=this_app,
    )

    assert [sr.id for sr in runs] == [mine.id]


def test_usage_leaves_out_the_machinery_a_run_spawns(
    transactional_db, force_authentication
):
    user = force_authentication
    workspace = user.get_or_create_personal_workspace()[0]
    published_run = _make_published_run(user, workspace)
    version = published_run.versions.first()
    kept = {
        surface: _make_sr(
            uid=user.uid,
            workspace=workspace,
            surface=surface,
            parent_version=version,
        ).id
        for surface in USAGE_SURFACES
    }
    for surface in (
        SavedRun.Surface.builder_child,
        SavedRun.Surface.tool_call,
        SavedRun.Surface.internal,
        SavedRun.Surface.analysis,
        SavedRun.Surface.export,
    ):
        _make_sr(
            uid=user.uid,
            workspace=workspace,
            surface=surface,
            parent_version=version,
        )

    runs = usage_runs(
        workflow=Workflow.VIDEO_BOTS,
        workspace=workspace,
        published_run=published_run,
    )

    assert sorted(sr.id for sr in runs) == sorted(kept.values())


def test_the_usage_grid_costs_one_query_however_many_cards(
    transactional_db, force_authentication, django_assert_num_queries
):
    """The card grid renders off `select_related` alone - no query per row.

    `_render_run_preview` used to cost a `get_or_create_from_uid` per card, and
    could create a user as a side effect of rendering a list. This is the test
    that would have caught it.
    """
    user = force_authentication
    workspace = user.get_or_create_personal_workspace()[0]
    # every workflow ever shipped has a metadata row; without one, rendering a
    # card falls back to `get_or_create_metadata`, which *writes* while listing
    WorkflowMetadata.objects.get_or_create(
        workflow=Workflow.VIDEO_BOTS,
        defaults=dict(short_title="Agent", meta_title="Agent", meta_description=""),
    )
    published_run = _make_published_run(user, workspace)
    _make_usage_runs(user, workspace, published_run, 3)

    with django_assert_num_queries(1):
        assert len(_render_usage_grid(user, workspace, published_run)) == 3

    _make_usage_runs(user, workspace, published_run, 9)

    with django_assert_num_queries(1):
        assert len(_render_usage_grid(user, workspace, published_run)) == 12


def _render_usage_grid(user, workspace, published_run) -> list:
    """What `_usage_tab` does, minus the pagination and the gui call."""
    qs = usage_runs(
        workflow=Workflow.VIDEO_BOTS,
        workspace=workspace,
        published_run=published_run,
    ).select_related(
        "parent_version__published_run",
        "workflow_metadata",
        "created_by",
        "message_thread__bot_conversation",
    )
    return [history_card(sr, author=author_from_user(sr.created_by, user)) for sr in qs]


def _make_usage_runs(user, workspace, published_run, n: int) -> None:
    integration = BotIntegration.objects.create(platform=Platform.WEB, name="test bi")
    for i in range(n):
        convo = Conversation.objects.create(
            bot_integration=integration, web_user_id=uuid.uuid4().hex
        )
        _make_sr(
            uid=user.uid,
            workspace=workspace,
            surface=SavedRun.Surface.deployment,
            parent_version=published_run.versions.first(),
            created_by=user,
            # a sender is only rendered for a run that carries a platform, so
            # without this the `message_thread__bot_conversation` join is never
            # walked and the assertion can't see it go missing
            platform=Platform.WEB,
            user_message_id=f"msg-{i}-{uuid.uuid4().hex}",
            message_thread=MessageThread.objects.create(
                title="hi", bot_conversation=convo
            ),
        )


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


def test_owning_a_run_does_not_unlock_someone_elses_usage(transactional_db):
    """Running somebody's public app must not hand you its Usage tab.

    The tab lists the *app's* workspace, so a run of it that happens to be yours says
    nothing about whether you may see the rest. This is the case the old
    `current_sr_user == user` clause let through.
    """
    from recipes.VideoBots_v2 import VideoBotsPageV2

    publisher = AppUser.objects.create(
        uid=uuid.uuid4().hex, email="alice@example.com", is_anonymous=False, balance=0
    )
    app_workspace = publisher.get_or_create_personal_workspace()[0]
    outsider = AppUser.objects.create(
        uid=uuid.uuid4().hex, email="bob@example.com", is_anonymous=False, balance=0
    )
    outsider.get_or_create_personal_workspace()

    def page_for(user):
        page = object.__new__(VideoBotsPageV2)
        page.request = SimpleNamespace(user=user)
        # the app's workspace, whoever is looking
        page._usage_workspace = lambda: app_workspace
        return page

    assert page_for(publisher).can_view_usage() is True
    assert page_for(outsider).can_view_usage() is False
    assert page_for(None).can_view_usage() is False
