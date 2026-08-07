import json
from datetime import timedelta

from django.utils import timezone

from bots.models import SavedRun, Workflow
from bots.models.message_thread import MessageThread
from daras_ai_v2.builder_analytics import (
    Outcome,
    build_error_stats,
    build_funnel,
    build_tool_stats,
    classify_outcome,
    get_builder_prompt_rows,
    get_live_activity,
    parse_transcript,
)


def _assistant(*calls: tuple[str, str, dict]) -> dict:
    """An assistant turn carrying tool calls, shaped like recipes/VideoBots.py writes it."""
    return dict(
        role="assistant",
        content="",
        tool_calls=[
            dict(
                id=call_id,
                type="function",
                function=dict(name=name, arguments=json.dumps(arguments)),
            )
            for call_id, name, arguments in calls
        ],
    )


def _tool_result(call_id: str, payload: dict) -> dict:
    return dict(role="tool", tool_call_id=call_id, content=json.dumps(payload))


def test_parse_transcript_pairs_calls_with_results():
    transcript = parse_transcript(
        [
            dict(role="user", content="build me a farming bot"),
            _assistant(("call_1", "search_workflows", {"search": "copilot"})),
            _tool_result("call_1", dict(results=[{"title": "Copilot"}])),
            _assistant(("call_2", "save_workflow", {"title": "Farm Bot"})),
            _tool_result(
                "call_2", dict(success=True, run_url="https://gooey.ai/farm-bot")
            ),
            dict(role="assistant", content="  Saved your workflow!  "),
        ]
    )

    assert transcript.tool_names() == ["search_workflows", "save_workflow"]
    assert all(call.ok for call in transcript.tool_calls)
    assert transcript.tool_calls[0].arguments == {"search": "copilot"}
    assert transcript.tool_calls[1].result_url == "https://gooey.ai/farm-bot"
    assert transcript.assistant_text == "Saved your workflow!"


def test_parse_transcript_detects_the_three_failure_shapes():
    transcript = parse_transcript(
        [
            # save tools return a bare error string
            _assistant(("call_1", "save_workflow", {})),
            _tool_result("call_1", dict(error="You can't update the root workflow")),
            # run_workflow returns a structured error
            _assistant(("call_2", "run_workflow", {})),
            _tool_result(
                "call_2", dict(error=dict(msg="Out of credits", type="UserError"))
            ),
            # the deploy tool returns success=False
            _assistant(("call_3", "deploy_workflow", {"platform": "nope"})),
            _tool_result("call_3", dict(success=False, error="Invalid platform")),
        ]
    )

    assert [call.ok for call in transcript.tool_calls] == [False, False, False]
    assert transcript.tool_calls[0].error == "You can't update the root workflow"
    assert transcript.tool_calls[1].error == "Out of credits"
    assert transcript.tool_calls[2].error == "Invalid platform"


def test_parse_transcript_treats_a_missing_success_key_as_success():
    # run_workflow returns the bare ResponseModel on success - no `success` key
    transcript = parse_transcript(
        [
            _assistant(("call_1", "run_workflow", {})),
            _tool_result("call_1", dict(output_text=["hello"])),
        ]
    )
    assert transcript.tool_calls[0].ok is True


def test_parse_transcript_leaves_unanswered_calls_undecided():
    # the run died before the tool came back
    transcript = parse_transcript([_assistant(("call_1", "save_workflow", {}))])
    assert transcript.tool_calls[0].ok is None
    assert transcript.tool_calls[0].status == "…"


def test_parse_transcript_survives_junk():
    # final_prompt is typed `list | str`, and tool content is free-form
    assert parse_transcript(None).tool_calls == []
    assert parse_transcript("a plain string prompt").tool_calls == []
    assert parse_transcript([None, 42, {"role": "assistant"}]).tool_calls == []
    assert parse_transcript([dict(role="assistant", tool_calls=[{}])]).tool_calls == []

    transcript = parse_transcript(
        [
            _assistant(("call_1", "save_workflow", {})),
            dict(role="tool", tool_call_id="call_1", content="not json at all"),
        ]
    )
    assert transcript.tool_calls[0].ok is None


def test_parse_transcript_keeps_unparseable_arguments():
    transcript = parse_transcript(
        [
            dict(
                role="assistant",
                tool_calls=[
                    dict(
                        id="call_1",
                        function=dict(name="save_workflow", arguments="{truncated"),
                    )
                ],
            )
        ]
    )
    assert transcript.tool_calls[0].arguments == {"_raw": "{truncated"}


def test_classify_outcome_reports_the_furthest_step_reached():
    deployed = parse_transcript(
        [
            _assistant(("call_1", "update_workflow_state", {})),
            _tool_result("call_1", dict(success=True)),
            _assistant(("call_2", "deploy_workflow", {"platform": "WHATSAPP"})),
            _tool_result("call_2", dict(success=True, deployment_url="https://x")),
        ]
    )
    assert (
        classify_outcome(transcript=deployed, error_msg="", run_status="")
        == Outcome.deployed
    )

    # a failed deploy falls back to the last step that did work
    partial = parse_transcript(
        [
            _assistant(("call_1", "save_workflow", {})),
            _tool_result("call_1", dict(success=True)),
            _assistant(("call_2", "deploy_workflow", {})),
            _tool_result("call_2", dict(success=False, error="nope")),
        ]
    )
    assert (
        classify_outcome(transcript=partial, error_msg="", run_status="")
        == Outcome.saved
    )


def test_classify_outcome_run_state_wins():
    transcript = parse_transcript([])
    assert (
        classify_outcome(transcript=transcript, error_msg="boom", run_status="")
        == Outcome.failed
    )
    assert (
        classify_outcome(transcript=transcript, error_msg="", run_status="Running...")
        == Outcome.running
    )
    # an error outranks a stale run_status
    assert (
        classify_outcome(transcript=transcript, error_msg="boom", run_status="Running…")
        == Outcome.failed
    )
    assert (
        classify_outcome(transcript=transcript, error_msg="", run_status="")
        == Outcome.answered
    )


def test_classify_outcome_all_tools_failed():
    transcript = parse_transcript(
        [
            _assistant(("call_1", "save_workflow", {})),
            _tool_result("call_1", dict(error="denied")),
        ]
    )
    assert (
        classify_outcome(transcript=transcript, error_msg="", run_status="")
        == Outcome.tool_error
    )


def test_build_funnel_counts_drop_off():
    rows = [
        # answered, no tools
        dict(transcript=parse_transcript([]), child_url=""),
        # tried a tool, it failed
        dict(
            transcript=parse_transcript(
                [
                    _assistant(("c", "run_workflow", {})),
                    _tool_result("c", dict(error="boom")),
                ]
            ),
            child_url="",
        ),
        # ran a workflow
        dict(
            transcript=parse_transcript(
                [
                    _assistant(("c", "run_workflow", {})),
                    _tool_result("c", dict(output_text=["hi"])),
                ]
            ),
            child_url="https://gooey.ai/run",
        ),
        # went all the way
        dict(
            transcript=parse_transcript(
                [
                    _assistant(("c1", "save_workflow", {})),
                    _tool_result("c1", dict(success=True)),
                    _assistant(("c2", "deploy_workflow", {})),
                    _tool_result("c2", dict(success=True)),
                ]
            ),
            child_url="https://gooey.ai/run",
        ),
    ]

    funnel = {step["step"]: step["count"] for step in build_funnel(rows)}
    assert funnel == {
        "Prompts": 4,
        "Tool attempted": 3,
        "Workflow touched": 2,
        "Saved": 1,
        "Deployed": 1,
    }
    assert build_funnel(rows)[0]["pct_of_prompts"] == 100.0
    assert build_funnel([])[0]["pct_of_prompts"] == 0.0


def test_build_tool_stats_success_rate_ignores_undecided_calls():
    rows = [
        dict(
            transcript=parse_transcript(
                [
                    _assistant(("c1", "save_workflow", {})),
                    _tool_result("c1", dict(success=True)),
                    _assistant(("c2", "save_workflow", {})),
                    _tool_result("c2", dict(error="denied")),
                    # never came back - shouldn't drag the success rate down
                    _assistant(("c3", "save_workflow", {})),
                ]
            )
        )
    ]
    stats = build_tool_stats(rows)
    assert stats == [
        dict(
            tool="save_workflow",
            calls=3,
            ok=1,
            failed=1,
            unknown=1,
            success_rate=50.0,
        )
    ]


def test_build_error_stats_counts_run_and_tool_errors():
    rows = [
        dict(
            error_type="UserError",
            error_msg="Out of credits",
            transcript=parse_transcript([]),
        ),
        dict(
            error_type="",
            error_msg="",
            transcript=parse_transcript(
                [
                    _assistant(("c1", "deploy_workflow", {})),
                    _tool_result("c1", dict(success=False, error="Invalid platform")),
                ]
            ),
        ),
        dict(
            error_type="",
            error_msg="",
            transcript=parse_transcript(
                [
                    _assistant(("c1", "deploy_workflow", {})),
                    _tool_result("c1", dict(success=False, error="Invalid platform")),
                ]
            ),
        ),
    ]
    stats = build_error_stats(rows)
    assert stats[0] == dict(
        source="tool: deploy_workflow", error="Invalid platform", count=2
    )
    assert dict(source="run", error="UserError", count=1) in stats


## db-backed ##################################################################


def _make_builder_prompt(user, workspace, *, prompt: str, final_prompt: list, **kwargs):
    return SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_id=f"builder-{prompt[:8]}-{timezone.now().timestamp()}",
        uid=user.uid,
        workspace=workspace,
        surface=SavedRun.Surface.builder_prompt,
        state=dict(input_prompt=prompt, final_prompt=final_prompt),
        **kwargs,
    )


def test_get_builder_prompt_rows(transactional_db, force_authentication):
    user = force_authentication
    workspace = user.get_or_create_personal_workspace()[0]

    thread = MessageThread.objects.create(title="Farming bot")
    builder_sr = _make_builder_prompt(
        user,
        workspace,
        prompt="build me a farming bot",
        final_prompt=[
            _assistant(("call_1", "save_workflow", {"title": "Farm Bot"})),
            _tool_result("call_1", dict(success=True, run_url="https://gooey.ai/farm")),
        ],
        message_thread=thread,
    )
    child = SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_id="child-run-1",
        uid=user.uid,
        workspace=workspace,
        surface=SavedRun.Surface.builder_child,
        parent_builder_saved_run=builder_sr,
    )
    # an ordinary run must not show up in the builder view
    SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_id="plain-run-1",
        uid=user.uid,
        workspace=workspace,
        surface=SavedRun.Surface.run,
    )

    now = timezone.now()
    rows, truncated = get_builder_prompt_rows(
        start=now - timedelta(hours=1), end=now + timedelta(hours=1)
    )

    assert truncated is False
    assert len(rows) == 1
    (row,) = rows
    assert row["input_prompt"] == "build me a farming bot"
    assert row["outcome"] == Outcome.saved
    assert row["thread_title"] == "Farming bot"
    assert row["transcript"].tool_names() == ["save_workflow"]
    assert child.run_id in row["child_url"]


def test_get_builder_prompt_rows_respects_the_window_and_limit(
    transactional_db, force_authentication
):
    user = force_authentication
    workspace = user.get_or_create_personal_workspace()[0]
    for i in range(3):
        _make_builder_prompt(user, workspace, prompt=f"prompt {i}", final_prompt=[])

    now = timezone.now()
    rows, truncated = get_builder_prompt_rows(
        start=now - timedelta(hours=1), end=now + timedelta(hours=1), limit=2
    )
    assert len(rows) == 2
    assert truncated is True

    # nothing in a window that ended before these runs were created
    rows, truncated = get_builder_prompt_rows(
        start=now - timedelta(days=2), end=now - timedelta(days=1)
    )
    assert rows == []
    assert truncated is False


def test_get_live_activity_covers_every_surface(transactional_db, force_authentication):
    user = force_authentication
    workspace = user.get_or_create_personal_workspace()[0]
    SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_id="plain-run-1",
        uid=user.uid,
        workspace=workspace,
        surface=SavedRun.Surface.run,
        state=dict(input_prompt="hello"),
    )
    SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_id="failed-run-1",
        uid=user.uid,
        workspace=workspace,
        surface=SavedRun.Surface.api,
        error_msg="boom",
    )

    now = timezone.now()
    rows = get_live_activity(
        start=now - timedelta(hours=1), end=now + timedelta(hours=1)
    )
    assert {row["run_id"] for row in rows} == {"plain-run-1", "failed-run-1"}
    by_id = {row["run_id"]: row for row in rows}
    assert by_id["plain-run-1"]["status"] == "✅ Done"
    assert by_id["plain-run-1"]["input_prompt"] == "hello"
    assert by_id["failed-run-1"]["status"] == "❌ Error"
    assert "plain-run-1" in by_id["plain-run-1"]["url"]

    rows = get_live_activity(
        start=now - timedelta(hours=1),
        end=now + timedelta(hours=1),
        surfaces=[SavedRun.Surface.api],
    )
    assert {row["run_id"] for row in rows} == {"failed-run-1"}
