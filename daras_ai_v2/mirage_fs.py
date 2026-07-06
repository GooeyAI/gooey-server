from __future__ import annotations

import asyncio
import re
import shlex
import typing
from dataclasses import dataclass

from pydantic import SecretStr

from daras_ai_v2.exceptions import UserError

S3_MOUNT_PATH = "/s3"

BLOCKED_COMMANDS = frozenset(
    {
        "cp",
        "mv",
        "rm",
        "rmdir",
        "mkdir",
        "touch",
        "chmod",
        "chown",
        "ln",
        "truncate",
        "tee",
        "dd",
        "install",
        "mktemp",
        "mkfifo",
        "shred",
        "rename",
        "write",
    }
)

REDIRECT_RE = re.compile(r"(?<![\\'\"])(?:>>?|<<|\d>>?|\d>>)")


@dataclass(frozen=True)
class ExecuteResult:
    stdout: str
    stderr: str
    exit_code: int


def run_readonly_s3_command(
    *,
    command: str,
    bucket: str,
    endpoint_url: str | None,
    region: str | None,
    prefix: str | None,
    access_key_id: str,
    secret_access_key: str,
) -> ExecuteResult:
    validate_readonly_command(command)
    return asyncio.run(
        _execute_readonly_s3_command(
            command=command,
            bucket=bucket,
            endpoint_url=endpoint_url,
            region=region,
            prefix=prefix,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
        )
    )


def validate_readonly_command(command: str) -> None:
    if not command or not command.strip():
        raise UserError("Please provide a bash command.")

    if REDIRECT_RE.search(command):
        raise UserError(
            "Write redirects are not allowed. This recipe only supports read-only commands."
        )

    for segment in _pipeline_segments(command):
        segment = segment.strip()
        if not segment:
            continue
        try:
            parts = shlex.split(segment)
        except ValueError as e:
            raise UserError(f"Invalid command syntax: {e}") from e
        if not parts:
            continue
        cmd = parts[0]
        if cmd in BLOCKED_COMMANDS:
            raise UserError(
                f"Command `{cmd}` is not allowed. This recipe only supports read-only commands "
                f"(e.g. ls, cat, grep, find, head, tail, wc)."
            )


def _pipeline_segments(command: str) -> list[str]:
    segments: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    escape = False

    for char in command:
        if escape:
            current.append(char)
            escape = False
            continue
        if char == "\\" and not in_single:
            escape = True
            current.append(char)
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            current.append(char)
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            current.append(char)
            continue
        if char == "|" and not in_single and not in_double:
            segments.append("".join(current))
            current = []
            continue
        current.append(char)

    segments.append("".join(current))
    return segments


async def _execute_readonly_s3_command(
    *,
    command: str,
    bucket: str,
    endpoint_url: str | None,
    region: str | None,
    prefix: str | None,
    access_key_id: str,
    secret_access_key: str,
) -> ExecuteResult:
    from mirage import Workspace
    from mirage.resource.s3 import S3Config, S3Resource

    config = S3Config(
        bucket=bucket,
        region=region or None,
        endpoint_url=endpoint_url or None,
        aws_access_key_id=SecretStr(access_key_id),
        aws_secret_access_key=SecretStr(secret_access_key),
        key_prefix=prefix or None,
    )
    ws = Workspace({S3_MOUNT_PATH: S3Resource(config)})
    try:
        result = await ws.execute(command)
    except Exception as e:
        raise UserError(f"Command failed: {e}") from e
    return await _coerce_io_result(result)


async def _coerce_io_result(result) -> ExecuteResult:
    if isinstance(result, ExecuteResult):
        return ExecuteResult(
            stdout=str(result.stdout or ""),
            stderr=str(result.stderr or ""),
            exit_code=int(result.exit_code or 0),
        )

    stdout = await _read_io_text(getattr(result, "stdout_str", None), getattr(result, "stdout", ""))
    stderr = await _read_io_text(getattr(result, "stderr_str", None), getattr(result, "stderr", ""))

    exit_code = getattr(result, "exit_code", 0) or 0
    if callable(exit_code):
        exit_code = 0

    return ExecuteResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=int(exit_code),
    )


async def _read_io_text(fn, fallback: typing.Any = "") -> str:
    if not callable(fn):
        return str(fallback or "")
    value = fn()
    if asyncio.iscoroutine(value):
        value = await value
    return str(value or "")
