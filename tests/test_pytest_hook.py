"""Tests for the parametrized test-suite hook."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from git_a_grip import pytest_hook

if TYPE_CHECKING:
    import pytest

RUNNER_EXIT_CODE = 2


def test_default_runner_is_uv_run_pytest() -> None:
    runner, args = pytest_hook.split_args(['tests/', '-q'])
    assert runner == ['uv', 'run', 'pytest']
    assert args == ['tests/', '-q']


def test_runner_flag_overrides_and_is_not_forwarded() -> None:
    runner, args = pytest_hook.split_args(
        ['--runner=uv run --extra api pytest', 'tests/', '-q'],
    )
    assert runner == ['uv', 'run', '--extra', 'api', 'pytest']
    assert args == ['tests/', '-q']


def test_empty_runner_fails_rather_than_running_nothing() -> None:
    assert pytest_hook.main(['--runner=']) == 1


def test_precommit_venv_pointers_are_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('VIRTUAL_ENV', '/tmp/precommit-hook-env')  # noqa: S108
    monkeypatch.setenv('PYTHONPATH', '/tmp/whatever')  # noqa: S108
    monkeypatch.setenv('KEEP_ME', 'yes')

    env = pytest_hook.clean_env()

    assert 'VIRTUAL_ENV' not in env
    assert 'PYTHONPATH' not in env
    assert env['KEEP_ME'] == 'yes'


def test_runs_from_the_repo_root_and_returns_the_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> object:
        calls.append({'cmd': cmd, **kwargs})
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=RUNNER_EXIT_CODE,
        )

    monkeypatch.setattr(pytest_hook, 'repo_root', lambda: '/repo')
    monkeypatch.setattr(pytest_hook.subprocess, 'run', fake_run)

    assert pytest_hook.main(['tests/', '-q']) == RUNNER_EXIT_CODE
    assert calls[0]['cmd'] == ['uv', 'run', 'pytest', 'tests/', '-q']
    assert calls[0]['cwd'] == '/repo'


def test_missing_runner_binary_reports_which_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(pytest_hook, 'repo_root', lambda: '/repo')
    monkeypatch.setattr(pytest_hook.subprocess, 'run', explode)

    assert pytest_hook.main([]) == 1
    assert "'uv'" in capsys.readouterr().err
