"""Tests for reaching the consuming project's environment."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from git_a_grip import project_env

if TYPE_CHECKING:
    import pytest


def test_the_default_runner_is_used_when_no_flag_is_given() -> None:
    runner, args = project_env.split_runner(['-q'], 'uv run pytest')

    assert runner == ['uv', 'run', 'pytest']
    assert args == ['-q']


def test_the_runner_flag_replaces_the_whole_command() -> None:
    runner, args = project_env.split_runner(
        ['--runner=uv run --group typing mypy', 'src'],
        'uv run mypy',
    )

    assert runner == ['uv', 'run', '--group', 'typing', 'mypy']
    assert args == ['src']


def test_the_runner_flag_is_not_forwarded_to_the_tool() -> None:
    # It configures the hook, not the tool, and every tool this reaches
    # would reject it.
    _, args = project_env.split_runner(['--runner=x', '-q'], 'default')

    assert args == ['-q']


def test_precommit_venv_pointers_are_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('VIRTUAL_ENV', '/tmp/precommit-hook-env')  # noqa: S108
    monkeypatch.setenv('PYTHONHOME', '/tmp/whatever')  # noqa: S108
    monkeypatch.setenv('PYTHONPATH', '/tmp/whatever')  # noqa: S108
    monkeypatch.setenv('KEEP_ME', 'yes')

    env = project_env.clean_env()

    assert 'VIRTUAL_ENV' not in env
    assert 'PYTHONHOME' not in env
    assert 'PYTHONPATH' not in env
    assert env['KEEP_ME'] == 'yes'


def test_the_repo_root_is_stripped_of_its_newline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        project_env.subprocess,
        'run',
        lambda *_a, **_k: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='/repo\n',
        ),
    )

    assert project_env.repo_root() == '/repo'


def test_no_repo_root_is_empty_rather_than_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Outside a working tree git says nothing on stdout. The callers turn
    # that into `cwd=None`, which is the right fallback -- refusing to run
    # would be a worse answer than running where the caller already is.
    monkeypatch.setattr(
        project_env.subprocess,
        'run',
        lambda *_a, **_k: subprocess.CompletedProcess(
            args=[],
            returncode=128,
            stdout='',
        ),
    )

    assert project_env.repo_root() == ''
