"""Tests for refusing a push straight onto a protected branch."""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import pytest

from git_a_grip import protect_branch

if TYPE_CHECKING:
    from pathlib import Path

_ENV = {
    'GIT_AUTHOR_NAME': 't',
    'GIT_AUTHOR_EMAIL': 't@example.com',
    'GIT_COMMITTER_NAME': 't',
    'GIT_COMMITTER_EMAIL': 't@example.com',
}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603
        ['git', '-C', str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        env=os.environ | _ENV,
    )


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv('PRE_COMMIT_REMOTE_BRANCH', raising=False)
    _git(tmp_path, 'init', '-q', '-b', 'main')
    _git(tmp_path, 'commit', '-q', '--allow-empty', '-m', 'x')
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize(
    ('branch', 'argv', 'expected'),
    [
        ('main', [], 1),
        ('master', [], 1),
        ('feature', [], 0),
        ('trunk', ['--branch=trunk'], 1),
        ('main', ['--branch=trunk'], 0),
        ('dev', ['--branch=trunk', '--branch=dev'], 1),
    ],
)
def test_protected_branches(
    repo: Path,
    branch: str,
    argv: list[str],
    expected: int,
) -> None:
    _git(repo, 'checkout', '-q', '-B', branch)

    assert protect_branch.main(argv) == expected


def test_origin_head_names_the_default(repo: Path) -> None:
    _git(repo, 'checkout', '-q', '-b', 'trunk')
    _git(repo, 'update-ref', 'refs/remotes/origin/trunk', 'HEAD')
    _git(
        repo,
        'symbolic-ref',
        'refs/remotes/origin/HEAD',
        'refs/remotes/origin/trunk',
    )

    assert protect_branch.main([]) == 1
    _git(repo, 'checkout', '-q', 'main')
    assert protect_branch.main([]) == 0


@pytest.mark.parametrize(
    ('checked_out', 'target', 'expected'),
    [
        ('feature', 'refs/heads/main', 1),
        ('main', 'refs/heads/feature', 0),
        ('main', 'refs/tags/v1.0', 0),
    ],
)
def test_the_push_target_decides_not_the_checkout(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    checked_out: str,
    target: str,
    expected: int,
) -> None:
    _git(repo, 'checkout', '-q', '-B', checked_out)
    monkeypatch.setenv('PRE_COMMIT_REMOTE_BRANCH', target)

    assert protect_branch.main([]) == expected


def test_detached_head_is_not_a_branch(repo: Path) -> None:
    _git(repo, 'checkout', '-q', '--detach')

    assert protect_branch.main([]) == 0


@pytest.mark.usefixtures('repo')
def test_refusal_says_how_to_get_out(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert protect_branch.main([]) == 1

    err = capsys.readouterr().err
    assert '`main`' in err
    assert 'git switch -c' in err
    assert 'git push' in err
    assert 'SKIP=protect-branch' in err


@pytest.mark.usefixtures('repo')
def test_unknown_argument_is_a_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert protect_branch.main(['--branch', 'main']) == 2  # noqa: PLR2004
    assert '--branch=' in capsys.readouterr().err
