from collections import defaultdict

from django.db import migrations

VIDEO_BOTS = 4  # Workflow.VIDEO_BOTS
SURFACE_RUN = 0  # SavedRun.Surface.run
SURFACE_BUILDER_CHILD = 4  # SavedRun.Surface.builder_child

ASSIGN_BATCH = 2000
CHUNK = 1000


def backfill_run_conversations(apps, schema_editor):
    """Group historical VideoBots runs into RunConversations.

    Replays the live grouping logic over existing runs in created_at order: each
    turn either continues its parent's conversation or starts a new one, using the
    same signal the runtime uses -- whether the turn was given a prior message
    history. Forward-only / best-effort (forks attach to the same conversation;
    runs whose parent isn't grouped start fresh).
    """
    SavedRun = apps.get_model("bots", "SavedRun")
    RunConversation = apps.get_model("bots", "RunConversation")
    db_alias = schema_editor.connection.alias

    # Backdate created_at/updated_at to the runs' own timestamps so the conversation
    # lists order by real activity, not migration time.
    _disable_auto_timestamps(RunConversation)

    convo_of_run = {}  # SavedRun.id -> RunConversation.id (parents seen so far)
    convo_scope = {}  # RunConversation.id -> (workspace_id, uid, surface)
    convo_title = {}  # RunConversation.id -> title (back-filled from later turns)
    convo_head = {}  # RunConversation.id -> (last_run_id, last_ts)
    pending = []  # (saved_run_id, conversation_id) to bulk-assign

    runs = (
        SavedRun.objects.using(db_alias)
        .filter(
            workflow=VIDEO_BOTS,
            conversation__isnull=True,
            surface__in=[SURFACE_RUN, SURFACE_BUILDER_CHILD],
        )
        .select_related("parent_builder_saved_run")
        .order_by("created_at", "id")
        .iterator(chunk_size=CHUNK)
    )
    for sr in runs:
        if sr.workspace_id is None:
            # RunConversation is workspace-scoped; can't group an orphan run.
            continue

        is_continuation, title = _run_signal(sr)

        # Mirror the live attach_run guard: only continue the parent's thread when
        # it shares this run's full scope (workflow is always VIDEO_BOTS here).
        convo_id = None
        if is_continuation and sr.parent_id:
            candidate = convo_of_run.get(sr.parent_id)
            if candidate is not None and convo_scope.get(candidate) == (
                sr.workspace_id,
                sr.uid or "",
                sr.surface,
            ):
                convo_id = candidate
        if convo_id is None:
            convo_id = (
                RunConversation.objects.using(db_alias)
                .create(
                    workspace_id=sr.workspace_id,
                    uid=sr.uid or "",
                    workflow=VIDEO_BOTS,
                    surface=sr.surface,
                    title=title,
                    created_at=sr.created_at,
                    updated_at=sr.created_at,
                )
                .id
            )
            convo_scope[convo_id] = (sr.workspace_id, sr.uid or "", sr.surface)
            convo_title[convo_id] = title
        elif not convo_title.get(convo_id) and title:
            # Mirror attach_run: fill a blank title from a later turn's prompt.
            convo_title[convo_id] = title

        convo_of_run[sr.id] = convo_id
        convo_head[convo_id] = (sr.id, sr.created_at)
        pending.append((sr.id, convo_id))
        if len(pending) >= ASSIGN_BATCH:
            _flush_assignments(db_alias, SavedRun, pending)
            pending = []

    _flush_assignments(db_alias, SavedRun, pending)
    _flush_heads(db_alias, RunConversation, convo_head, convo_title)


def _run_signal(sr):
    """(is_continuation, title) inferred from stored state, per the live signals.

    Playground turns carry their own prior `messages`; builder turns carry them on
    the builder-prompt run that produced them. An empty history => new conversation.
    """
    if sr.surface == SURFACE_BUILDER_CHILD:
        prompt_sr = sr.parent_builder_saved_run
        state = (prompt_sr.state if prompt_sr else None) or {}
    else:
        state = sr.state or {}
    return bool(state.get("messages")), (state.get("input_prompt") or "").strip()


def _flush_assignments(db_alias, SavedRun, pending):
    by_convo = defaultdict(list)
    for sr_id, convo_id in pending:
        by_convo[convo_id].append(sr_id)
    for convo_id, sr_ids in by_convo.items():
        SavedRun.objects.using(db_alias).filter(id__in=sr_ids).update(
            conversation_id=convo_id
        )


def _flush_heads(db_alias, RunConversation, convo_head, convo_title):
    for convo_id, (last_run_id, last_ts) in convo_head.items():
        RunConversation.objects.using(db_alias).filter(id=convo_id).update(
            last_run_id=last_run_id, updated_at=last_ts, title=convo_title[convo_id]
        )


def _disable_auto_timestamps(RunConversation):
    for name in ("created_at", "updated_at"):
        field = RunConversation._meta.get_field(name)
        field.auto_now = False
        field.auto_now_add = False


class Migration(migrations.Migration):
    dependencies = [
        ("bots", "0127_runconversation_savedrun_conversation_and_more"),
    ]

    operations = [
        migrations.RunPython(
            backfill_run_conversations, migrations.RunPython.noop
        ),
    ]
