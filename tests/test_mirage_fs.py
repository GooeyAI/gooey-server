import pytest
from unittest.mock import AsyncMock, patch

from daras_ai_v2.exceptions import UserError
from daras_ai_v2.mirage_fs import (
    ExecuteResult,
    _coerce_io_result,
    run_readonly_s3_command,
    validate_readonly_command,
)


@pytest.mark.parametrize(
    "command",
    [
        "ls /s3/",
        "grep alert /s3/logs/*.jsonl | wc -l",
        "find /s3/data -name '*.jsonl'",
        "cat /s3/report.csv",
        "head -n 10 /s3/logs/app.log",
    ],
)
def test_validate_readonly_command_allows_read_commands(command: str):
    validate_readonly_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "cp /s3/a /s3/b",
        "mv /s3/a /s3/b",
        "rm /s3/file.txt",
        "mkdir /s3/new",
        "touch /s3/file.txt",
        "echo hi > /s3/out.txt",
        "grep x /s3/a >> /s3/b",
        "cat /s3/a | tee /s3/b",
    ],
)
def test_validate_readonly_command_blocks_mutating_commands(command: str):
    with pytest.raises(UserError):
        validate_readonly_command(command)


def test_validate_readonly_command_requires_non_empty_command():
    with pytest.raises(UserError, match="provide a bash command"):
        validate_readonly_command("   ")


@patch("daras_ai_v2.mirage_fs._execute_readonly_s3_command", new_callable=AsyncMock)
def test_run_readonly_s3_command_returns_execute_result(mock_execute: AsyncMock):
    mock_execute.return_value = ExecuteResult(
        stdout="ok\n",
        stderr="",
        exit_code=0,
    )

    result = run_readonly_s3_command(
        command="ls /s3/",
        bucket="my-bucket",
        endpoint_url=None,
        region="us-east-1",
        prefix=None,
        access_key_id="key",
        secret_access_key="secret",
    )

    assert result.stdout == "ok\n"
    assert result.exit_code == 0
    assert isinstance(result.stdout, str)
    mock_execute.assert_awaited_once()


def test_execute_result_is_json_serializable():
    import json

    result = ExecuteResult(stdout="hello", stderr="", exit_code=0)
    json.dumps({"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.exit_code})


class _FakeIOResult:
    exit_code = 0

    async def stdout_str(self):
        return "listed\n"

    async def stderr_str(self):
        return ""


def test_coerce_io_result_awaits_mirage_methods():
    import asyncio

    result = asyncio.run(_coerce_io_result(_FakeIOResult()))
    assert result.stdout == "listed\n"
    assert result.stderr == ""
    assert result.exit_code == 0
