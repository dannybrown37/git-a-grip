"""Tests for the release command's ordering and exit codes."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from git_a_grip import release

if TYPE_CHECKING:
    import pytest

BUMP_FAILURE_CODE = 7
PUSH_FAILURE_CODE = 128
UNKNOWN_ARG_CODE = 2


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


def _arrange(
    monkeypatch: pytest.MonkeyPatch,
    *,
    branch: str = 'main',
    dirty: bool = False,
    bump_code: int = 0,
    push_code: int = 0,
) -> list[str]:
    """Stub git and cz, returning the ordered log of what was invoked."""
    log: list[str] = []

    def fake_git(*args: str) -> subprocess.CompletedProcess[str]:
        if args[0] == 'push':
            log.append(' '.join(args))
            return _completed(returncode=push_code, stderr='push boom')
        return _completed()

    def fake_cz(*args: str) -> subprocess.CompletedProcess[str]:
        if 'version' in args:
            return _completed(stdout='0.3.0')
        log.append(' '.join(args))
        return _completed(returncode=bump_code)

    monkeypatch.setattr(release, 'git', fake_git)
    monkeypatch.setattr(release, 'current_branch', lambda: branch)
    monkeypatch.setattr(release, 'is_dirty', lambda: dirty)
    monkeypatch.setattr(release.cz, 'run', fake_cz)
    return log


def test_bumps_then_pushes_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point: exit 0, with the bump ordered before the push."""
    log = _arrange(monkeypatch)

    assert release.main([]) == 0
    assert log == [
        'bump --yes --no-verify',
        'push --no-verify --follow-tags origin main',
    ]


def test_reports_the_released_version(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _arrange(monkeypatch)
    release.main([])
    assert 'v0.3.0' in capsys.readouterr().out


def test_nothing_to_release_still_pushes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = _arrange(monkeypatch, bump_code=release.NO_COMMITS_FOUND)

    assert release.main([]) == 0
    assert log[-1] == 'push --no-verify --follow-tags origin main'


def test_feature_branch_pushes_without_bumping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = _arrange(monkeypatch, branch='feature/x')

    assert release.main([]) == 0
    assert log == ['push --no-verify --follow-tags origin feature/x']


def test_dirty_tree_refuses_before_touching_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = _arrange(monkeypatch, dirty=True)

    assert release.main([]) == 1
    assert log == []


def test_bump_failure_propagates_without_pushing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = _arrange(monkeypatch, bump_code=BUMP_FAILURE_CODE)

    assert release.main([]) == BUMP_FAILURE_CODE
    assert 'push' not in ' '.join(log)


def test_push_failure_after_a_bump_is_reported(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _arrange(monkeypatch, push_code=PUSH_FAILURE_CODE)

    assert release.main([]) == PUSH_FAILURE_CODE
    assert 'bumped to v0.3.0 locally' in capsys.readouterr().err


def test_help_prints_usage_without_releasing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    log = _arrange(monkeypatch)

    assert release.main(['--help']) == 0
    assert log == []
    assert 'gag release' in capsys.readouterr().out


def test_unknown_argument_refuses_to_release(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A publishing command must not treat an unknown flag as consent."""
    log = _arrange(monkeypatch)

    assert release.main(['--dry-run']) == UNKNOWN_ARG_CODE
    assert log == []
    assert '--dry-run' in capsys.readouterr().err
