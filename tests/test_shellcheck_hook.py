"""Tests for the shell script lint hook."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from git_a_grip import shellcheck_hook

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _calls(
    monkeypatch: pytest.MonkeyPatch,
    code: int = 0,
) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> object:
        calls.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=code)

    monkeypatch.setattr(
        shellcheck_hook,
        'shellcheck_path',
        lambda: '/bin/shellcheck',
    )
    monkeypatch.setattr(shellcheck_hook.subprocess, 'run', fake_run)
    return calls


def _script(tmp_path: Path, name: str = 'build.sh') -> str:
    path = tmp_path / name
    path.write_text('#!/usr/bin/env bash\necho hi\n')
    return str(path)


def test_it_lints_the_files_pre_commit_passed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = _calls(monkeypatch)
    script = _script(tmp_path)

    assert shellcheck_hook.main([script]) == 0
    assert calls == [['/bin/shellcheck', script]]


def test_args_reach_the_tool_in_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = _calls(monkeypatch)
    script = _script(tmp_path)

    assert shellcheck_hook.main(['--severity=warning', script]) == 0
    assert calls == [['/bin/shellcheck', '--severity=warning', script]]


def test_findings_fail_the_commit_with_shellchecks_own_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # shellcheck has already printed what it found, in its own words.
    _calls(monkeypatch, 1)

    assert shellcheck_hook.main([_script(tmp_path)]) == 1
    assert capsys.readouterr().err == ''


def test_no_files_is_a_pass_not_a_usage_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # shellcheck given no files exits 3 with its usage text.
    calls = _calls(monkeypatch)

    assert shellcheck_hook.main([]) == 0
    assert shellcheck_hook.main(['--severity=warning']) == 0
    assert calls == []


def test_a_missing_binary_says_where_it_comes_from(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(shellcheck_hook, 'shellcheck_path', lambda: None)

    assert shellcheck_hook.main([_script(tmp_path)]) == 1
    assert 'additional_dependencies' in capsys.readouterr().err


def test_the_hook_env_copy_wins_over_one_on_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binary = tmp_path / 'shellcheck'
    binary.write_text('')
    binary.chmod(0o755)
    monkeypatch.setattr(
        shellcheck_hook.sys,
        'executable',
        str(tmp_path / 'python'),
    )
    monkeypatch.setattr(
        shellcheck_hook.shutil,
        'which',
        lambda _n: '/usr/bin/sc',
    )

    assert shellcheck_hook.shellcheck_path() == str(binary)


def test_it_falls_back_to_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        shellcheck_hook.sys,
        'executable',
        str(tmp_path / 'python'),
    )
    monkeypatch.setattr(
        shellcheck_hook.shutil,
        'which',
        lambda _n: '/usr/bin/sc',
    )

    assert shellcheck_hook.shellcheck_path() == '/usr/bin/sc'
