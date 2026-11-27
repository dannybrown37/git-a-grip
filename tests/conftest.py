"""Fixtures shared across test modules."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _git(*args: str | Path) -> None:
    subprocess.run(  # noqa: S603
        [  # noqa: S607
            'git',
            '-c',
            'init.defaultBranch=main',
            '-c',
            'user.name=t',
            '-c',
            'user.email=t@t',
            *map(str, args),
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def clone_with_worktree(tmp_path: Path) -> tuple[Path, Path]:
    """A real clone at projects/alpha, plus a linked worktree beside it.

    Real git rather than a hand-written `.git` file, because a worktree is
    something git builds and these tests guard against how git builds it.
    """
    clone = tmp_path / 'projects' / 'alpha'
    clone.mkdir(parents=True)
    worktree = tmp_path / 'projects' / 'alpha-worktrees' / 'feat'
    _git('init', clone)
    _git('-C', clone, 'commit', '--allow-empty', '-m', 'init')
    _git('-C', clone, 'worktree', 'add', worktree, '-b', 'feat')
    return clone.resolve(), worktree.resolve()


def _config(rev: str) -> str:
    return (
        'repos:\n'
        '  - repo: https://github.com/dannybrown37/git-a-grip\n'
        f'    rev: {rev}\n'
        '    hooks:\n'
        '      - id: commitizen-early\n'
    )


@pytest.fixture
def stale_clone(tmp_path: Path) -> Path:
    """A clone at projects/alpha that fetched a bump but never pulled it.

    The working tree pins v0.3.1; origin/main pins v0.4.0. That is the
    everyday state of a repo you have not touched since its last release.
    """
    upstream = tmp_path / 'upstream.git'
    seed = tmp_path / 'seed'
    clone = tmp_path / 'projects' / 'alpha'
    _git('init', '--bare', upstream)
    _git('clone', upstream, seed)
    (seed / '.pre-commit-config.yaml').write_text(_config('v0.3.1'))
    _git('-C', seed, 'add', '.')
    _git('-C', seed, 'commit', '-m', 'pin v0.3.1')
    _git('-C', seed, 'push', 'origin', 'HEAD:main')
    _git('clone', upstream, clone)
    (seed / '.pre-commit-config.yaml').write_text(_config('v0.4.0'))
    _git('-C', seed, 'commit', '-am', 'pin v0.4.0')
    _git('-C', seed, 'push', 'origin', 'HEAD:main')
    _git('-C', clone, 'fetch')
    return clone.resolve()


@pytest.fixture
def git() -> Callable[..., None]:
    """Run git in a test, with an identity and a fixed default branch."""
    return _git
