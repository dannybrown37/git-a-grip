"""Tests for the ruff hooks' fix-then-restage behaviour."""

from __future__ import annotations

from pathlib import Path

import pytest

from git_a_grip import ruff_hooks


@pytest.fixture
def staged(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Record what would have been re-staged instead of calling git."""
    calls: list[list[str]] = []
    monkeypatch.setattr(
        ruff_hooks.restage,
        'add',
        lambda paths: calls.append(paths) or 0,
    )
    return calls


def _ruff_that(
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int = 0,
    rewrites: dict[str, str] | None = None,
) -> list[tuple[str, ...]]:
    """Stub the ruff invocation, optionally rewriting files as ruff would."""
    invocations: list[tuple[str, ...]] = []

    def fake_ruff(*args: str) -> int:
        invocations.append(args)
        for name, content in (rewrites or {}).items():
            Path(name).write_text(content)
        return returncode

    monkeypatch.setattr(ruff_hooks, '_ruff', fake_ruff)
    return invocations


def test_rewritten_files_are_restaged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    staged: list[list[str]],
) -> None:
    monkeypatch.chdir(tmp_path)
    Path('a.py').write_text('x=1\n')
    _ruff_that(monkeypatch, rewrites={'a.py': 'x = 1\n'})

    assert ruff_hooks.run('format', ['a.py']) == 0
    assert staged == [['a.py']]


def test_untouched_files_are_not_restaged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    staged: list[list[str]],
) -> None:
    monkeypatch.chdir(tmp_path)
    Path('a.py').write_text('x = 1\n')
    _ruff_that(monkeypatch)

    assert ruff_hooks.run('format', ['a.py']) == 0
    assert staged == []


def test_unfixable_violations_still_fail_after_restaging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    staged: list[list[str]],
) -> None:
    # `ruff check --fix` fixed one file but left a violation it cannot fix:
    # the fix is committed, the commit still stops.
    monkeypatch.chdir(tmp_path)
    Path('a.py').write_text('import os\n')
    _ruff_that(monkeypatch, returncode=1, rewrites={'a.py': 'x = 1\n'})

    assert ruff_hooks.run('check', ['--fix', 'a.py']) == 1
    assert staged == [['a.py']]


def test_force_exclude_is_passed_before_the_hook_args(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    staged: list[list[str]],
) -> None:
    monkeypatch.chdir(tmp_path)
    Path('a.py').write_text('x = 1\n')
    invocations = _ruff_that(monkeypatch)

    ruff_hooks.run('check', ['--fix', '--config', 'cfg.toml', 'a.py'])

    assert staged == []
    assert invocations == [
        ('check', '--force-exclude', '--fix', '--config', 'cfg.toml', 'a.py'),
    ]


def test_a_failed_restage_fails_the_hook(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path('a.py').write_text('x=1\n')
    _ruff_that(monkeypatch, rewrites={'a.py': 'x = 1\n'})
    monkeypatch.setattr(ruff_hooks.restage, 'add', lambda _paths: 128)

    assert ruff_hooks.run('format', ['a.py']) == 1
