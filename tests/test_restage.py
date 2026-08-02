"""Tests for narrowing a hook's `git add` to the files it actually rewrote."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from git_a_grip import restage

if TYPE_CHECKING:
    import pytest


def test_target_paths_keeps_existing_files_and_drops_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path('a.py').write_text('x = 1\n')
    args = ['--fix', '--config', 'missing.toml', 'a.py', 'gone.py']
    assert restage.target_paths(args) == ['a.py']


def test_target_paths_picks_up_flag_values_that_are_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Harmless: an unchanged config never reaches `changed()`.
    monkeypatch.chdir(tmp_path)
    Path('.ruff.toml').write_text('line-length = 79\n')
    assert restage.target_paths(['--config', '.ruff.toml']) == ['.ruff.toml']


def test_changed_reports_only_rewritten_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path('touched.py').write_text('x=1\n')
    Path('untouched.py').write_text('y = 2\n')
    paths = ['touched.py', 'untouched.py']

    before = restage.digests(paths)
    Path('touched.py').write_text('x = 1\n')

    assert restage.changed(before, restage.digests(paths)) == ['touched.py']


def test_digests_skips_unreadable_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert restage.digests(['nope.py']) == {}


def test_add_is_a_no_op_without_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        msg = 'git should not be invoked'
        raise AssertionError(msg)

    monkeypatch.setattr(restage.subprocess, 'run', explode)
    assert restage.add([]) == 0
