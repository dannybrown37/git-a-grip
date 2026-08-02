"""Tests for the pre-push bump hook's decision logic."""

from __future__ import annotations

import subprocess

import pytest

from git_a_grip import bump_on_push

BUMP_FAILURE_CODE = 7


def _completed(
    returncode: int = 0,
    stdout: str = '',
    stderr: str = '',
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


@pytest.fixture
def on_clean_main(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Pretend we are on a clean `main`, recording any git push."""
    pushes: list[str] = []
    monkeypatch.setattr(bump_on_push, 'current_branch', lambda: 'main')
    monkeypatch.setattr(bump_on_push, 'is_dirty', lambda: False)

    def fake_git(*args: str) -> subprocess.CompletedProcess[str]:
        if args and args[0] == 'push':
            pushes.append(' '.join(args))
        return _completed()

    monkeypatch.setattr(bump_on_push, '_git', fake_git)
    return pushes


def test_skips_non_default_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bump_on_push, 'current_branch', lambda: 'feature')
    assert bump_on_push.main() == 0


def test_refuses_dirty_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bump_on_push, 'current_branch', lambda: 'main')
    monkeypatch.setattr(bump_on_push, 'is_dirty', lambda: True)
    assert bump_on_push.main() == 1


@pytest.mark.parametrize(
    'code',
    [bump_on_push.NO_COMMITS_FOUND, bump_on_push.NONE_INCREMENT],
)
def test_nothing_to_release_lets_push_proceed(
    code: int,
    on_clean_main: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No bumpable commits must pass the push through, not fail it."""
    monkeypatch.setattr(
        bump_on_push.cz,
        'run',
        lambda *_: _completed(returncode=code),
    )
    assert bump_on_push.main() == 0
    assert on_clean_main == []


def test_bump_failure_propagates(
    on_clean_main: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bump_on_push.cz,
        'run',
        lambda *_: _completed(returncode=BUMP_FAILURE_CODE, stderr='boom'),
    )
    assert bump_on_push.main() == BUMP_FAILURE_CODE
    assert on_clean_main == []


def test_successful_bump_pushes_then_cancels(
    on_clean_main: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hook must push the bumped ref, then fail the original push."""
    monkeypatch.setattr(
        bump_on_push.cz,
        'run',
        lambda *args: _completed(stdout='0.2.0' if 'version' in args else ''),
    )
    assert bump_on_push.main() == 1
    assert on_clean_main == [
        'push --no-verify --follow-tags origin main',
    ]
