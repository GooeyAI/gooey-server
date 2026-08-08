from __future__ import annotations

import datetime
import json
import typing
from dataclasses import dataclass, field

from django.db.models import QuerySet
from django.db.models.fields.json import KeyTextTransform

from app_users.models import AppUser
from bots.models import MessageThread, SavedRun, Workflow
from workspaces.models import Workspace

# Parsing a transcript means pulling the whole `final_prompt` JSON blob out of the
# row, so the number of rows we're willing to do that for is deliberately bounded.
# Views that hit this cap say so instead of silently reporting partial numbers.
MAX_ANALYZED_RUNS = 2000

# Rows are read in chunks so a wide window never materializes every transcript at
# once - each one is reduced to a handful of fields and thrown away.
_ITER_CHUNK_SIZE = 100

# The tools the Gooey Builder exposes to the LLM, grouped by what a successful
# call actually accomplishes for the user. See functions/gooey_builder_tools.py.
SEARCH_TOOLS = frozenset({"search_workflows", "fetch_workflow_state"})
EDIT_TOOLS = frozenset({"update_workflow_state"})
RUN_TOOLS = frozenset({"run_workflow"})
SAVE_TOOLS = frozenset({"save_workflow", "save_as_new_workflow"})
DEPLOY_TOOLS = frozenset({"deploy_workflow"})

BUILDER_TOOLS = SEARCH_TOOLS | EDIT_TOOLS | RUN_TOOLS | SAVE_TOOLS | DEPLOY_TOOLS


class Outcome:
    """What the user walked away with from a single builder prompt.

    Ordered by how far down the funnel it is - `classify_outcome` reports the
    furthest step a prompt reached.
    """

    running = "⏳ Running"
    failed = "❌ Run failed"
    tool_error = "⚠️ Tool error"
    answered = "💬 Answered"
    searched = "🔍 Searched"
    edited = "✏️ Edited workflow"
    ran = "▶️ Ran workflow"
    saved = "💾 Saved workflow"
    deployed = "🚀 Deployed"

    #: display order, least to most complete
    funnel_order = [
        running,
        failed,
        tool_error,
        answered,
        searched,
        edited,
        ran,
        saved,
        deployed,
    ]


@dataclass
class ToolCall:
    name: str
    arguments: dict = field(default_factory=dict)
    #: None when the transcript has no matching result - the run was still going,
    #: or errored out before the tool returned.
    ok: bool | None = None
    error: str = ""
    result_url: str = ""

    @property
    def status(self) -> str:
        if self.ok is None:
            return "…"
        return "✅" if self.ok else "❌"

    def __str__(self) -> str:
        return f"{self.status} {self.name}"


@dataclass
class Transcript:
    tool_calls: list[ToolCall] = field(default_factory=list)
    assistant_text: str = ""

    def tool_names(self) -> list[str]:
        return [call.name for call in self.tool_calls]

    def succeeded(self, names: typing.Container[str]) -> bool:
        return any(call.ok and call.name in names for call in self.tool_calls)

    def result_url(self, names: typing.Container[str]) -> str:
        for call in reversed(self.tool_calls):
            if call.ok and call.name in names and call.result_url:
                return call.result_url
        return ""


def parse_transcript(final_prompt: typing.Any) -> Transcript:
    """Recover the tool calls (and whether each one worked) from a builder run.

    Builder tool calls aren't persisted anywhere queryable - the only record is
    the LLM transcript saved in ``SavedRun.state["final_prompt"]``, where each
    assistant turn carries ``tool_calls`` and every result comes back as a
    ``role="tool"`` message keyed by ``tool_call_id``.
    See recipes/VideoBots.py:llm_loop.

    Tolerates anything - `final_prompt` is typed as `list | str` and the tool
    payloads are free-form JSON produced by whatever the tool returned.
    """
    transcript = Transcript()
    if not isinstance(final_prompt, list):
        return transcript

    calls_by_id: dict[str, ToolCall] = {}
    for entry in final_prompt:
        if not isinstance(entry, dict):
            continue

        match entry.get("role"):
            case "assistant":
                content = entry.get("content")
                if isinstance(content, str) and content.strip():
                    transcript.assistant_text = content.strip()
                for raw_call in entry.get("tool_calls") or ():
                    call = _parse_tool_call(raw_call)
                    if not call:
                        continue
                    transcript.tool_calls.append(call)
                    # only dicts survive _parse_tool_call, so this is safe
                    call_id = raw_call.get("id")
                    if call_id:
                        calls_by_id[call_id] = call

            case "tool":
                call = calls_by_id.get(entry.get("tool_call_id") or "")
                if call:
                    _apply_tool_result(call, entry.get("content"))

    return transcript


def _parse_tool_call(raw_call: typing.Any) -> ToolCall | None:
    if not isinstance(raw_call, dict):
        return None
    fn = raw_call.get("function")
    if not isinstance(fn, dict):
        return None
    name = fn.get("name")
    if not name:
        return None

    arguments = fn.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except (ValueError, TypeError):
            arguments = {"_raw": arguments}
    if not isinstance(arguments, dict):
        arguments = {}

    return ToolCall(name=str(name), arguments=arguments)


def _apply_tool_result(call: ToolCall, content: typing.Any) -> None:
    """Read a tool's JSON result the way the builder tools write it.

    Failures are signalled either by a truthy ``error`` key (a string from
    most tools, a dict from ``run_workflow``) or by ``success: False`` from
    the deploy tool. Anything else that parsed is a success - ``run_workflow``
    returns the bare response with no ``success`` key at all.
    """
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (ValueError, TypeError):
            # not JSON - can't tell success from failure, leave ok unset
            return
    if not isinstance(content, dict):
        return

    error = content.get("error")
    if error:
        call.ok = False
        if isinstance(error, dict):
            call.error = str(error.get("msg") or error.get("type") or error)
        else:
            call.error = str(error)
        return
    if content.get("success") is False:
        call.ok = False
        call.error = "failed"
        return

    call.ok = True
    for key in ("run_url", "deployment_url", "workflow_url"):
        url = content.get(key)
        if url:
            call.result_url = str(url)
            break


def classify_outcome(*, transcript: Transcript, error_msg: str, run_status: str) -> str:
    """The furthest step a single builder prompt got to."""
    if error_msg:
        return Outcome.failed
    if run_status:
        return Outcome.running

    if transcript.succeeded(DEPLOY_TOOLS):
        return Outcome.deployed
    if transcript.succeeded(SAVE_TOOLS):
        return Outcome.saved
    if transcript.succeeded(RUN_TOOLS):
        return Outcome.ran
    if transcript.succeeded(EDIT_TOOLS):
        return Outcome.edited
    if transcript.succeeded(SEARCH_TOOLS):
        return Outcome.searched
    if transcript.tool_calls:
        # every tool call either failed or never came back
        return Outcome.tool_error
    return Outcome.answered


def build_funnel(rows: list[dict]) -> list[dict]:
    """Drop-off across the builder's steps, widest first.

    Each step counts prompts that got *at least* this far, so the funnel stays
    monotonic: saving a workflow implies touching one, deploying implies saving.
    Testing each step in isolation would let a prompt that saved without a
    separate edit/run step make "Saved" wider than "Workflow touched", which
    renders as an inverted funnel.
    """
    total = len(rows)
    steps = [
        ("Prompts", lambda r: True),
        ("Tool attempted", lambda r: bool(r["transcript"].tool_calls)),
        (
            "Workflow touched",
            lambda r: (
                r["transcript"].succeeded(
                    EDIT_TOOLS | RUN_TOOLS | SAVE_TOOLS | DEPLOY_TOOLS
                )
                or bool(r["child_url"])
            ),
        ),
        ("Saved", lambda r: r["transcript"].succeeded(SAVE_TOOLS | DEPLOY_TOOLS)),
        ("Deployed", lambda r: r["transcript"].succeeded(DEPLOY_TOOLS)),
    ]
    funnel = []
    for label, predicate in steps:
        count = sum(1 for row in rows if predicate(row))
        funnel.append(
            dict(
                step=label,
                count=count,
                pct_of_prompts=round(100 * count / total, 1) if total else 0.0,
            )
        )
    return funnel


def build_tool_stats(rows: list[dict]) -> list[dict]:
    """Per-tool call volume and success rate, most-used first."""
    stats: dict[str, dict] = {}
    for row in rows:
        for call in row["transcript"].tool_calls:
            entry = stats.setdefault(
                call.name, dict(tool=call.name, calls=0, ok=0, failed=0, unknown=0)
            )
            entry["calls"] += 1
            if call.ok is None:
                entry["unknown"] += 1
            elif call.ok:
                entry["ok"] += 1
            else:
                entry["failed"] += 1

    for entry in stats.values():
        decided = entry["ok"] + entry["failed"]
        entry["success_rate"] = (
            round(100 * entry["ok"] / decided, 1) if decided else None
        )
    return sorted(stats.values(), key=lambda e: -e["calls"])


def build_error_stats(rows: list[dict]) -> list[dict]:
    """Top failure modes, counting run-level errors and tool-level errors alike."""
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        if row["error_type"] or row["error_msg"]:
            key = ("run", row["error_type"] or "Unknown")
            counts[key] = counts.get(key, 0) + 1
        for call in row["transcript"].tool_calls:
            if call.ok is False:
                key = ("tool: " + call.name, _truncate(call.error, 120) or "Unknown")
                counts[key] = counts.get(key, 0) + 1
    return sorted(
        (
            dict(source=source, error=error, count=count)
            for (source, error), count in counts.items()
        ),
        key=lambda e: -e["count"],
    )


def get_builder_prompt_rows(
    *,
    start: datetime.datetime,
    end: datetime.datetime,
    uids: QuerySet | list[str] | None = None,
    limit: int = MAX_ANALYZED_RUNS,
) -> tuple[list[dict], bool]:
    """Every Gooey Builder prompt in the window, with its parsed outcome.

    Returns ``(rows, truncated)`` - `truncated` is True when the window held more
    prompts than `limit`, so the caller can say the numbers are a recent sample
    rather than the whole window.
    """
    qs = (
        SavedRun.objects.filter(
            surface=SavedRun.Surface.builder_prompt,
            created_at__gte=start,
            created_at__lt=end,
        )
        .annotate(input_prompt=KeyTextTransform("input_prompt", "state"))
        .order_by("-created_at")
    )
    if uids is not None:
        qs = qs.filter(uid__in=uids)

    truncated = qs.count() > limit

    fields = [
        "id",
        "run_id",
        "uid",
        "workspace_id",
        "workflow",
        "message_thread_id",
        "created_at",
        "updated_at",
        "run_time",
        "run_status",
        "price",
        "error_msg",
        "error_type",
        "input_prompt",
    ]
    rows = []
    # `state` is a fat JSONB blob; only `final_prompt` is worth transferring, and
    # only for the bounded set of rows we're about to parse. Stream it in chunks
    # and stop at `limit` rather than slicing, so a wide window never buffers
    # every transcript at once.
    for values in (
        qs.annotate(final_prompt=KeyTextTransform("final_prompt", "state"))
        .values(*fields, "final_prompt")
        .iterator(chunk_size=_ITER_CHUNK_SIZE)
    ):
        if len(rows) >= limit:
            break
        final_prompt = values.pop("final_prompt", None)
        if isinstance(final_prompt, str):
            try:
                final_prompt = json.loads(final_prompt)
            except (ValueError, TypeError):
                final_prompt = None
        transcript = parse_transcript(final_prompt)
        rows.append(
            values
            | dict(
                transcript=transcript,
                child_url="",
                thread_title="",
                outcome=classify_outcome(
                    transcript=transcript,
                    error_msg=values["error_msg"],
                    run_status=values["run_status"],
                ),
            )
        )

    _attach_child_runs(rows)
    _attach_thread_titles(rows)
    return rows, truncated


def _attach_child_runs(rows: list[dict]) -> None:
    """Link each prompt to the workflow run it produced, in one extra query."""
    if not rows:
        return
    children = (
        SavedRun.objects.filter(
            parent_builder_saved_run_id__in=[row["id"] for row in rows]
        )
        .values("parent_builder_saved_run_id", "workflow", "run_id", "uid")
        .order_by("created_at")
    )
    # ordered oldest first, so a prompt that spawned several runs keeps the latest
    by_parent = {child["parent_builder_saved_run_id"]: child for child in children}
    for row in rows:
        child = by_parent.get(row["id"])
        if child:
            row["child_url"] = build_run_url(
                workflow=child["workflow"], run_id=child["run_id"], uid=child["uid"]
            )
        else:
            # the builder can save or deploy without ever creating a child run,
            # in which case the only link is the url the tool handed back
            row["child_url"] = row["transcript"].result_url(BUILDER_TOOLS)


def _attach_thread_titles(rows: list[dict]) -> None:
    thread_ids = {row["message_thread_id"] for row in rows if row["message_thread_id"]}
    if not thread_ids:
        return
    titles = dict(
        MessageThread.objects.filter(id__in=thread_ids).values_list("id", "title")
    )
    for row in rows:
        row["thread_title"] = titles.get(row["message_thread_id"]) or ""


def get_live_activity(
    *,
    start: datetime.datetime,
    end: datetime.datetime,
    surfaces: list[int] | None = None,
    uids: QuerySet | list[str] | None = None,
    limit: int = 200,
) -> list[dict]:
    """Most recent runs across every surface - the raw interaction feed.

    Deliberately skips transcript parsing so it stays cheap enough to poll.
    """
    qs = SavedRun.objects.filter(
        created_at__gte=start, created_at__lt=end, run_id__isnull=False
    )
    if surfaces:
        qs = qs.filter(surface__in=surfaces)
    if uids is not None:
        qs = qs.filter(uid__in=uids)

    values = (
        qs.annotate(input_prompt=KeyTextTransform("input_prompt", "state"))
        .order_by("-created_at")
        .values(
            "run_id",
            "uid",
            "workspace_id",
            "workflow",
            "surface",
            "created_at",
            "run_time",
            "run_status",
            "price",
            "error_msg",
            "error_type",
            "input_prompt",
        )[:limit]
    )
    return [
        row
        | dict(
            status=run_status_label(
                error_msg=row["error_msg"], run_status=row["run_status"]
            ),
            url=build_run_url(
                workflow=row["workflow"], run_id=row["run_id"], uid=row["uid"]
            ),
        )
        for row in values
    ]


def run_status_label(*, error_msg: str, run_status: str) -> str:
    if error_msg:
        return "❌ Error"
    if run_status:
        return f"⏳ {run_status}"
    return "✅ Done"


def build_run_url(*, workflow: int, run_id: str | None, uid: str | None) -> str:
    if not run_id:
        return ""
    try:
        page_cls = Workflow(workflow).page_cls
    except (ValueError, KeyError):
        return ""
    return str(page_cls.raw_app_url(query_params=dict(run_id=run_id, uid=uid)))


def workflow_label(workflow: int) -> str:
    try:
        return Workflow(workflow).label
    except ValueError:
        return str(workflow)


def get_user_labels(uids: typing.Iterable[str]) -> dict[str, str]:
    """uid -> a human-readable name, in one query."""
    uids = {uid for uid in uids if uid}
    if not uids:
        return {}
    return {
        user["uid"]: (
            user["display_name"] or user["email"] or user["phone_number"] or user["uid"]
        )
        for user in AppUser.objects.filter(uid__in=uids).values(
            "uid", "display_name", "email", "phone_number"
        )
    }


def get_workspace_labels(workspace_ids: typing.Iterable[int]) -> dict[int, str]:
    """workspace id -> display name, in one query."""
    workspace_ids = {wid for wid in workspace_ids if wid}
    if not workspace_ids:
        return {}
    return {
        workspace.id: workspace.display_name()
        for workspace in Workspace.objects.filter(id__in=workspace_ids).select_related(
            "created_by"
        )
    }


def _truncate(text: str, maxlen: int) -> str:
    text = (text or "").strip().replace("\n", " ")
    if len(text) > maxlen:
        return text[: maxlen - 1] + "…"
    return text
