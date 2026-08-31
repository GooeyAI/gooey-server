"""
An MCP (Model Context Protocol) server that exposes Gooey's copilot analytics,
so Claude Desktop / Claude Code can query and analyse bot data directly.

It does not touch the database itself. Every tool shells out to
`scripts/analytics_cli.py`, which runs inside the gooey-server virtualenv and
reuses the same querysets as the copilot "Stats" page, so the numbers here
always match the UI.

The two halves are separate processes on purpose: the `mcp` package requires
uvicorn >= 0.31, while gooey-server pins uvicorn ^0.18.3, so `mcp` cannot be
installed into the gooey-server environment without upgrading the production
ASGI server. This file therefore imports nothing from gooey-server and lives in
its own small virtualenv.

Setup -- create a virtualenv that holds only the MCP SDK::

    python3 -m venv .mcp-venv
    .mcp-venv/bin/pip install "mcp>=2"

Then point it at the gooey-server interpreter with two environment variables:

``GOOEY_PYTHON``
    Path to the gooey-server virtualenv's python. Required.
``GOOEY_REPO``
    Path to the gooey-server checkout. Defaults to this file's parent directory.

Register it with Claude Code, from the repo root::

    claude mcp add gooey \\
      -e GOOEY_PYTHON="$(poetry env info -e)" \\
      -e GOOEY_REPO="$PWD" \\
      -- "$PWD/.mcp-venv/bin/python" "$PWD/scripts/mcp_server.py"

Or with Claude Desktop, in ``claude_desktop_config.json``::

    {
      "mcpServers": {
        "gooey": {
          "command": "/path/to/gooey-server/.mcp-venv/bin/python",
          "args": ["/path/to/gooey-server/scripts/mcp_server.py"],
          "env": {
            "GOOEY_PYTHON": "/path/to/gooey-virtualenv/bin/python",
            "GOOEY_REPO": "/path/to/gooey-server"
          }
        }
      }
    }

This server is read-only, but it has no workspace scoping -- it grants whatever
the configured ``DATABASE_URL`` grants, and message content is end-user data.
Point it at a local database or a read replica, not a production primary.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

REPO = Path(os.environ.get("GOOEY_REPO") or Path(__file__).resolve().parent.parent)
GOOEY_PYTHON = os.environ.get("GOOEY_PYTHON")
CLI = REPO / "scripts" / "analytics_cli.py"
TIMEOUT_SEC = 300

mcp = MCPServer(
    name="gooey",
    instructions=(
        "Query Gooey.AI copilot analytics: bot integrations, conversations, "
        "messages, user feedback, and the LLM analysis results attached to "
        "messages.\n\n"
        "Start with `list_bots` to find a bot's numeric id, then `bot_stats` "
        "for headline numbers and `sample_messages` for a quick look at the "
        "conversation data.\n\n"
        "For any real analysis, call `export_table` and read the CSV it writes "
        "with pandas -- do not try to pull thousands of rows through "
        "`sample_messages`. Use `sql` (read-only SELECT) for aggregations the "
        "other tools do not cover, calling `describe_tables` first to learn the "
        "schema."
    ),
)


@mcp.tool()
def list_bots(
    search: str | None = None,
    platform: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List copilot integrations, most recently updated first.

    Args:
        search: Optional case-insensitive substring matched against the bot name.
        platform: Optional platform filter, one of FACEBOOK, INSTAGRAM, WHATSAPP,
            SLACK, WEB, TWILIO, TELEGRAM.
        limit: Maximum number of bots to return.

    Returns:
        One dict per bot, including the `id` that every other tool takes.
    """
    return _run("list-bots", search=search, platform=platform, limit=limit)


@mcp.tool()
def bot_stats(
    bot_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Headline engagement numbers for one bot, matching its Stats page.

    Args:
        bot_id: The `id` from `list_bots`.
        start_date: Optional inclusive start date, as YYYY-MM-DD.
        end_date: Optional inclusive end date, as YYYY-MM-DD.

    Returns:
        User, conversation, message and feedback counts. The active-user figures
        are always relative to today, not to the date range.
    """
    return _run("bot-stats", bot_id=bot_id, start_date=start_date, end_date=end_date)


@mcp.tool()
def sample_messages(
    bot_id: int,
    limit: int = 20,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Read a small sample of message pairs for a bot, inline.

    Each row pairs a user message with the bot's reply and carries the analysis
    result, feedback, run time and credits for that turn.

    Args:
        bot_id: The `id` from `list_bots`.
        limit: Rows to return, capped at 200. Use `export_table` for bulk.
        start_date: Optional inclusive start date, as YYYY-MM-DD.
        end_date: Optional inclusive end date, as YYYY-MM-DD.
    """
    return _run(
        "sample-messages",
        bot_id=bot_id,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
    )


@mcp.tool()
def export_table(
    bot_id: int,
    details: str = "Messages",
    start_date: str | None = None,
    end_date: str | None = None,
    rows: int = 10000,
    out_dir: str | None = None,
) -> dict:
    """Export a bot's data to a CSV on disk, for analysis with pandas.

    This is the tool to use for anything beyond a glance: it writes the whole
    table to a file and returns the path, so large exports never have to travel
    through the conversation.

    Args:
        bot_id: The `id` from `list_bots`.
        details: Which table to export. One of "Messages", "Conversations",
            "Feedback Positive", "Feedback Negative", "Answered Successfully",
            "Answered Unsuccessfully".
        start_date: Inclusive start date as YYYY-MM-DD. Pass both dates or neither.
        end_date: Inclusive end date as YYYY-MM-DD. Pass both dates or neither.
        rows: Maximum number of rows to export.
        out_dir: Directory to write into. Defaults to `exports/` in the repo.

    Returns:
        The CSV `path`, the `row_count`, and the `columns` it contains.
    """
    return _run(
        "export-table",
        bot_id=bot_id,
        details=details,
        start_date=start_date,
        end_date=end_date,
        rows=rows,
        out_dir=out_dir,
    )


@mcp.tool()
def sql(query: str, limit: int = 200) -> dict:
    """Run a read-only SELECT against the Gooey database.

    Use this for aggregations the other tools do not cover. Call
    `describe_tables` first to get table and column names. The query runs in a
    read-only transaction that is always rolled back, and only a single
    SELECT/WITH statement is accepted.

    Args:
        query: A single SELECT (or WITH ... SELECT) statement.
        limit: Maximum rows to return, capped at 1000.

    Returns:
        The `columns`, the `rows` as a list of dicts, and whether the result was
        `truncated`.
    """
    return _run("sql", query=query, limit=limit)


@mcp.tool()
def describe_tables(app_labels: list[str] | None = None) -> list[dict]:
    """Describe the database schema, for writing queries against `sql`.

    Args:
        app_labels: Django apps to describe. Defaults to the ones holding
            analytics data: bots, app_users, workspaces, usage_costs.

    Returns:
        One dict per model with its `table` name and `columns`, each column
        listing its type and, for foreign keys, the table it points at.
    """
    return _run("describe-tables", app_labels=app_labels)


def _run(command: str, **kwargs):
    """Invoke `scripts/analytics_cli.py` in the gooey-server env and parse its JSON.

    Failures are raised as `ToolError`: the SDK keeps the message of a
    `ToolError` but replaces the text of any other exception with a generic
    "Error executing tool", which would hide the CLI's validation messages.
    """
    if not GOOEY_PYTHON:
        raise ToolError(
            "GOOEY_PYTHON is not set. Point it at the gooey-server virtualenv's "
            "python, e.g. the output of `poetry env info -e`."
        )
    # drop unset optionals so the CLI's own defaults apply
    args = {k: v for k, v in kwargs.items() if v is not None}
    try:
        proc = subprocess.run(
            [GOOEY_PYTHON, str(CLI), command, json.dumps(args)],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
        )
    except FileNotFoundError:
        raise ToolError(f"GOOEY_PYTHON does not exist: {GOOEY_PYTHON}")
    except subprocess.TimeoutExpired:
        raise ToolError(
            f"{command} timed out after {TIMEOUT_SEC}s. Narrow the date range, "
            f"or lower `limit`/`rows`."
        )

    stdout = proc.stdout.strip()
    if not stdout:
        raise ToolError(
            f"{command} produced no output (exit {proc.returncode}). "
            f"stderr: {proc.stderr.strip()[-2000:]}"
        )
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        raise ToolError(
            f"{command} produced invalid JSON (exit {proc.returncode}): {stdout[:500]}"
        )
    if isinstance(result, dict) and "error" in result:
        raise ToolError(result["error"])
    return result


if __name__ == "__main__":
    print(f"gooey mcp server: repo={REPO} python={GOOEY_PYTHON}", file=sys.stderr)
    mcp.run(transport="stdio")
