"""
Read-only analytics queries over Gooey's copilot data, emitted as JSON.

This is the ORM half of the MCP server in `scripts/mcp_server.py`. It runs
inside the gooey-server virtualenv (it needs Django and the app's models),
takes one command plus a JSON blob of arguments, and prints a single JSON
document to stdout::

    python scripts/analytics_cli.py list-bots '{"limit": 5}'
    python scripts/analytics_cli.py bot-stats '{"bot_id": 1}'

The two halves are split because the `mcp` package requires a far newer uvicorn
than this project pins, so it cannot be installed alongside gooey-server. Only
this file touches the ORM; only `scripts/mcp_server.py` imports `mcp`, and it
shells out to this one.

Everything here is read-only: each command either runs a SELECT or writes a CSV.
There is no workspace scoping, so this grants whatever `DATABASE_URL` grants.
"""

import sys

# anything Django (or an app import) prints on the way up would corrupt the JSON
# on stdout, so send it to stderr and keep the real stdout for the result
_stdout = sys.stdout
sys.stdout = sys.stderr

__import__("gooeysite.wsgi")  # Note: this must always be at the top

import datetime  # noqa: E402
import json  # noqa: E402
import traceback  # noqa: E402
import typing  # noqa: E402
from pathlib import Path  # noqa: E402

import pytz  # noqa: E402
from django.apps import apps  # noqa: E402
from django.db import connection, transaction  # noqa: E402

from bots.models import BotIntegration, Conversation, Message, Platform  # noqa: E402
from daras_ai_v2 import settings  # noqa: E402

DETAILS_CHOICES = [
    "Messages",
    "Conversations",
    "Feedback Positive",
    "Feedback Negative",
    "Answered Successfully",
    "Answered Unsuccessfully",
]
MAX_SQL_ROWS = 1000
MAX_SAMPLE_ROWS = 200
DEFAULT_EXPORT_DIR = Path(settings.BASE_DIR) / "exports"


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(
            f"usage: {argv[0]} <{'|'.join(COMMANDS)}> ['<json args>']", file=sys.stderr
        )
        return 2
    command = argv[1]
    if command not in COMMANDS:
        return _fail(f"Unknown command {command!r}, expected one of {list(COMMANDS)}")
    try:
        kwargs = json.loads(argv[2]) if len(argv) > 2 and argv[2] else {}
    except json.JSONDecodeError as e:
        return _fail(f"Arguments must be a JSON object: {e}")
    if not isinstance(kwargs, dict):
        return _fail("Arguments must be a JSON object")
    try:
        result = COMMANDS[command](**kwargs)
    except TypeError as e:
        return _fail(f"Bad arguments for {command}: {e}")
    except ValueError as e:
        return _fail(str(e))
    except Exception as e:
        # anything else is a genuine crash: keep the traceback on stderr for
        # debugging, but still hand the caller a parseable error
        traceback.print_exc()
        return _fail(f"{command} failed: {type(e).__name__}: {e}")
    print(json.dumps(result, default=str), file=_stdout)
    return 0


def list_bots(
    search: str | None = None,
    platform: str | None = None,
    limit: int = 50,
) -> list[dict]:
    qs = BotIntegration.objects.select_related(
        "workspace", "published_run", "saved_run"
    ).order_by("-updated_at")
    if search:
        qs = qs.filter(name__icontains=search)
    if platform:
        try:
            qs = qs.filter(platform=Platform[platform.upper()])
        except KeyError:
            raise ValueError(
                f"Unknown platform {platform!r}, expected one of "
                f"{[p.name for p in Platform]}"
            )
    return [
        {
            "id": bi.id,
            "name": bi.name,
            "display_name": bi.get_display_name(),
            "platform": Platform(bi.platform).label,
            "workspace": bi.workspace and bi.workspace.name,
            "copilot": bi.published_run and bi.published_run.title,
            "created_at": bi.created_at.isoformat(),
            "updated_at": bi.updated_at.isoformat(),
        }
        for bi in qs[:limit]
    ]


def bot_stats(
    bot_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    from recipes.VideoBotsStats import (
        compute_overall_stats,
        get_conversations_and_messages,
    )

    bi = _get_bot(bot_id)
    conversations, messages = get_conversations_and_messages(bi)
    conversations, messages = _filter_by_date(
        conversations, messages, start_date, end_date
    )
    stats = compute_overall_stats(
        bi=bi,
        conversations=conversations,
        messages=messages,
        start_date=_parse_date(start_date),
        end_date=_parse_date(end_date),
    )
    return {
        "bot_id": bi.id,
        "name": bi.name,
        "platform": Platform(bi.platform).label,
        "start_date": start_date,
        "end_date": end_date,
        **stats,
    }


def sample_messages(
    bot_id: int,
    limit: int = 20,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    bi = _get_bot(bot_id)
    _, messages = _filter_by_date(
        Conversation.objects.filter(bot_integration=bi).order_by(),
        Message.objects.filter(conversation__bot_integration=bi).order_by(),
        start_date,
        end_date,
    )
    limit = max(1, min(limit, MAX_SAMPLE_ROWS))
    # to_json's row_limit counts messages, but each row pairs a user message
    # with the bot's reply, so scan double and slice back to `limit` rows.
    return messages.to_json(tz=_tz(), row_limit=limit * 2)[:limit]


def export_table(
    bot_id: int,
    details: str = "Messages",
    start_date: str | None = None,
    end_date: str | None = None,
    rows: int = 10000,
    out_dir: str | None = None,
) -> dict:
    from recipes.VideoBotsStats import get_conversations_and_messages, get_tabular_data

    if details not in DETAILS_CHOICES:
        raise ValueError(f"details must be one of {DETAILS_CHOICES}, got {details!r}")
    if bool(start_date) != bool(end_date):
        # get_tabular_data only applies a range when both ends are given, and
        # would otherwise silently export everything.
        raise ValueError("Pass both start_date and end_date, or neither")

    bi = _get_bot(bot_id)
    conversations, messages = get_conversations_and_messages(bi)
    df = get_tabular_data(
        bi=bi,
        tz=_tz(),
        conversations=conversations,
        messages=messages,
        details=details,
        sort_by=None,
        rows=rows,
        start_date=_parse_date(start_date),
        end_date=_parse_date(end_date),
    )

    out = Path(out_dir) if out_dir else DEFAULT_EXPORT_DIR
    out.mkdir(parents=True, exist_ok=True)
    slug = details.lower().replace(" ", "-")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out / f"gooey-{bi.id}-{slug}-{stamp}.csv"
    df.to_csv(path, index=False)

    return {
        "path": str(path),
        "row_count": len(df),
        "columns": list(df.columns),
        "bot": bi.name,
        "details": details,
    }


def sql(query: str, limit: int = 200) -> dict:
    query = _validate_select(query)
    limit = max(1, min(limit, MAX_SQL_ROWS))
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(query)
            columns = [col[0] for col in cursor.description]
            records = cursor.fetchmany(limit + 1)
        transaction.set_rollback(True)
    truncated = len(records) > limit
    return {
        "columns": columns,
        "rows": [dict(zip(columns, record)) for record in records[:limit]],
        "truncated": truncated,
    }


def describe_tables(app_labels: list[str] | None = None) -> list[dict]:
    app_labels = app_labels or ["bots", "app_users", "workspaces", "usage_costs"]
    out = []
    for label in app_labels:
        try:
            app_config = apps.get_app_config(label)
        except LookupError:
            raise ValueError(
                f"Unknown app {label!r}. Installed apps: "
                f"{sorted(c.label for c in apps.get_app_configs())}"
            )
        for model in app_config.get_models():
            out.append(
                {
                    "model": f"{label}.{model.__name__}",
                    "table": model._meta.db_table,
                    "columns": [
                        {
                            "name": field.column,
                            "type": field.get_internal_type(),
                            "references": (
                                field.related_model._meta.db_table
                                if field.is_relation and field.related_model
                                else None
                            ),
                        }
                        for field in model._meta.fields
                    ],
                }
            )
    return out


def _fail(message: str) -> int:
    print(json.dumps({"error": message}), file=_stdout)
    return 1


def _get_bot(bot_id: int) -> BotIntegration:
    try:
        return BotIntegration.objects.select_related("published_run").get(id=bot_id)
    except BotIntegration.DoesNotExist:
        raise ValueError(f"No bot integration with id {bot_id}. Try `list-bots` first.")


def _filter_by_date(
    conversations: typing.Any,
    messages: typing.Any,
    start_date: str | None,
    end_date: str | None,
) -> tuple[typing.Any, typing.Any]:
    start, end = _parse_date(start_date), _parse_date(end_date)
    if start:
        messages = messages.filter(created_at__date__gte=start)
    if end:
        messages = messages.filter(created_at__date__lte=end)
    if start or end:
        conversations = conversations.filter(messages__in=messages).distinct()
    return conversations, messages


def _parse_date(value: str | None) -> datetime.date | None:
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"Invalid date {value!r}, expected YYYY-MM-DD")


def _validate_select(query: str) -> str:
    query = query.strip().rstrip(";").strip()
    if not query:
        raise ValueError("Empty query")
    if ";" in query:
        raise ValueError("Only a single statement is allowed")
    if not query.lower().startswith(("select", "with")):
        raise ValueError("Only SELECT (or WITH ... SELECT) queries are allowed")
    return query


def _tz():
    return pytz.timezone(settings.TIME_ZONE)


COMMANDS = {
    "list-bots": list_bots,
    "bot-stats": bot_stats,
    "sample-messages": sample_messages,
    "export-table": export_table,
    "sql": sql,
    "describe-tables": describe_tables,
}


if __name__ == "__main__":
    sys.exit(main(sys.argv))
