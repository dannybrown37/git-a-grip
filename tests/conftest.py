"""Fixtures shared across test modules."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
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
