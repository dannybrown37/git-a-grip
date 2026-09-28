"""Tests for the shell script format hook."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from git_a_grip import shfmt_hook

if TYPE_CHECKING:
    import pytest

PARSE_ERROR_EXIT = 1


def _calls(
    monkeypatch: pytest.MonkeyPatch,
    code: int = 0,
    rewrites: dict[str, str] | None = None,
) -> list[list[str]]:
    """Capture what the hook runs, rewriting files as shfmt -w would."""
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> object:
        calls.append(cmd)
        for path, text in (rewrites or {}).items():
            Path(path).write_text(text)
        return subprocess.CompletedProcess(args=cmd, returncode=code)

    monkeypatch.setattr(shfmt_hook, 'shfmt_path', lambda: '/bin/shfmt')
    monkeypatch.setattr(shfmt_hook.subprocess, 'run', fake_run)
    monkeypatch.setattr(shfmt_hook.restage, 'add', lambda _paths: 0)
    return calls


def _script(tmp_path: Path, name: str = 'build.sh') -> str:
    path = tmp_path / name
    path.write_text('if true;then\necho  hi\nfi\n')
    return str(path)


def test_it_writes_in_place_over_the_files_pre_commit_passed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Without -w shfmt prints the formatted script to stdout and leaves
    # the file as it was -- a hook that passes and fixes nothing.
    calls = _calls(monkeypatch)
    script = _script(tmp_path)

    assert shfmt_hook.main([script]) == 0
    assert calls == [['/bin/shfmt', '-w', script]]


def test_args_reach_the_tool_in_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = _calls(monkeypatch)
    script = _script(tmp_path)

    assert shfmt_hook.main(['-i', '2', '-ci', script]) == 0
    assert calls == [['/bin/shfmt', '-w', '-i', '2', '-ci', script]]


def test_a_rewritten_script_is_re_staged_and_passes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The package's contract: the fix is already in the commit, so failing
    # would only make the author run the same command twice.
    script = _script(tmp_path)
    _calls(monkeypatch, rewrites={script: 'if true; then\n\techo hi\nfi\n'})
    staged: list[list[str]] = []
    monkeypatch.setattr(
        shfmt_hook.restage,
        'add',
        lambda paths: staged.append(paths) or 0,
    )

    assert shfmt_hook.main([script]) == 0
    assert staged == [[script]]
    assert script in capsys.readouterr().err


def test_an_untouched_script_is_not_re_staged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _calls(monkeypatch)
    staged: list[list[str]] = []
    monkeypatch.setattr(
        shfmt_hook.restage,
        'add',
        lambda paths: staged.append(paths) or 0,
    )

    assert shfmt_hook.main([_script(tmp_path)]) == 0
    assert staged == []


def test_a_parse_error_fails_with_shfmts_own_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # A script shfmt cannot parse is the one thing it cannot fix.
    _calls(monkeypatch, PARSE_ERROR_EXIT)

    assert shfmt_hook.main([_script(tmp_path)]) == PARSE_ERROR_EXIT


def test_a_failed_re_stage_fails_the_hook(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _script(tmp_path)
    _calls(monkeypatch, rewrites={script: 'echo hi\n'})
    monkeypatch.setattr(shfmt_hook.restage, 'add', lambda _paths: 1)

    assert shfmt_hook.main([script]) == 1
    assert 're-stage' in capsys.readouterr().err


def test_no_files_never_reaches_shfmt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # shfmt given no files reads stdin, which would hang the commit.
    calls = _calls(monkeypatch)

    assert shfmt_hook.main([]) == 0
    assert shfmt_hook.main(['-i', '2']) == 0
    assert calls == []


def test_a_missing_binary_says_where_it_comes_from(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(shfmt_hook, 'shfmt_path', lambda: None)

    assert shfmt_hook.main([_script(tmp_path)]) == 1
    assert 'additional_dependencies' in capsys.readouterr().err


def test_the_hook_env_copy_wins_over_one_on_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binary = tmp_path / 'shfmt'
    binary.write_text('')
    binary.chmod(0o755)
    monkeypatch.setattr(shfmt_hook.sys, 'executable', str(tmp_path / 'py'))
    monkeypatch.setattr(shfmt_hook.shutil, 'which', lambda _n: '/usr/bin/s')

    assert shfmt_hook.shfmt_path() == str(binary)


def test_it_falls_back_to_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(shfmt_hook.sys, 'executable', str(tmp_path / 'py'))
    monkeypatch.setattr(shfmt_hook.shutil, 'which', lambda _n: '/usr/bin/s')

    assert shfmt_hook.shfmt_path() == '/usr/bin/s'
