"""Tests for the GitHub Actions audit hook."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from git_a_grip import zizmor_hook

if TYPE_CHECKING:
    import pytest

FINDINGS_EXIT = 14


def _calls(
    monkeypatch: pytest.MonkeyPatch,
    code: int = 0,
    rewrites: dict[str, str] | None = None,
) -> list[list[str]]:
    """Capture what the hook runs, rewriting files as zizmor --fix would."""
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> object:
        calls.append(cmd)
        for path, text in (rewrites or {}).items():
            Path(path).write_text(text)
        return subprocess.CompletedProcess(args=cmd, returncode=code)

    monkeypatch.setattr(zizmor_hook, 'zizmor_path', lambda: '/bin/zizmor')
    monkeypatch.setattr(zizmor_hook.subprocess, 'run', fake_run)
    monkeypatch.setattr(zizmor_hook.restage, 'add', lambda _paths: 0)
    return calls


def _workflow(tmp_path: Path, name: str = 'ci.yml') -> str:
    path = tmp_path / name
    path.write_text('on: push\n')
    return str(path)


def test_it_audits_the_files_pre_commit_passed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Unlike mypy and tsc, zizmor has no project config saying what to
    # check -- it audits what it is handed, so the staged list is the list.
    calls = _calls(monkeypatch)
    workflow = _workflow(tmp_path)

    assert zizmor_hook.main([workflow]) == 0
    assert calls[0] == ['/bin/zizmor', workflow]


def test_args_reach_the_tool_in_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = _calls(monkeypatch)
    workflow = _workflow(tmp_path)

    assert zizmor_hook.main(['--min-severity=medium', workflow]) == 0
    assert calls[0] == ['/bin/zizmor', '--min-severity=medium', workflow]


def test_findings_fail_the_commit_with_zizmors_own_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # zizmor has already printed what it found, in its own words.
    _calls(monkeypatch, FINDINGS_EXIT)

    assert zizmor_hook.main([_workflow(tmp_path)]) == FINDINGS_EXIT
    assert capsys.readouterr().err == ''


def test_no_files_is_a_pass_not_a_usage_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # zizmor with no input exits 2 with its usage text. Reaching it would
    # fail a commit for a hook that had nothing to audit.
    calls = _calls(monkeypatch)

    assert zizmor_hook.main([]) == 0
    assert zizmor_hook.main(['--persona=pedantic']) == 0
    assert calls == []


def test_a_fixed_workflow_is_re_staged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The package's contract: what a hook rewrote is part of the commit,
    # not a dirty working tree behind a failure.
    workflow = _workflow(tmp_path)
    _calls(monkeypatch, rewrites={workflow: 'on: push\npermissions: {}\n'})
    staged: list[list[str]] = []
    monkeypatch.setattr(
        zizmor_hook.restage,
        'add',
        lambda paths: staged.append(paths) or 0,
    )

    assert zizmor_hook.main(['--fix', workflow]) == 0
    assert staged == [[workflow]]
    assert workflow in capsys.readouterr().err


def test_an_untouched_workflow_is_not_re_staged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _calls(monkeypatch)
    staged: list[list[str]] = []
    monkeypatch.setattr(
        zizmor_hook.restage,
        'add',
        lambda paths: staged.append(paths) or 0,
    )

    assert zizmor_hook.main([_workflow(tmp_path)]) == 0
    assert staged == []


def test_a_failed_re_stage_fails_the_hook(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = _workflow(tmp_path)
    _calls(monkeypatch, rewrites={workflow: 'on: pull_request\n'})
    monkeypatch.setattr(zizmor_hook.restage, 'add', lambda _paths: 1)

    assert zizmor_hook.main(['--fix', workflow]) == 1
    assert 're-stage' in capsys.readouterr().err


def test_a_missing_binary_says_where_it_comes_from(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(zizmor_hook, 'zizmor_path', lambda: None)

    assert zizmor_hook.main([_workflow(tmp_path)]) == 1
    assert 'additional_dependencies' in capsys.readouterr().err


def test_the_hook_env_copy_wins_over_one_on_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # zizmor is a binary, so `sys.executable -m` is not available -- looking
    # beside the interpreter is what pins the hook to the copy pre-commit
    # installed for it rather than whatever the machine has.
    binary = tmp_path / 'zizmor'
    binary.write_text('')
    binary.chmod(0o755)
    monkeypatch.setattr(
        zizmor_hook.sys,
        'executable',
        str(tmp_path / 'python'),
    )
    monkeypatch.setattr(zizmor_hook.shutil, 'which', lambda _n: '/usr/bin/z')

    assert zizmor_hook.zizmor_path() == str(binary)


def test_it_falls_back_to_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        zizmor_hook.sys,
        'executable',
        str(tmp_path / 'python'),
    )
    monkeypatch.setattr(zizmor_hook.shutil, 'which', lambda _n: '/usr/bin/z')

    assert zizmor_hook.zizmor_path() == '/usr/bin/z'
