"""Tests for recovering a commit message out of `git commit` argv."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from git_a_grip.commitizen_early import message_from_argv


@pytest.mark.parametrize(
    ('argv', 'expected'),
    [
        (['git', 'commit', '-m', 'feat: a'], 'feat: a'),
        (['git', 'commit', '--message', 'feat: a'], 'feat: a'),
        (['git', 'commit', '--message=feat: a'], 'feat: a'),
        (['git', 'commit', '-mfeat: a'], 'feat: a'),
        (['git', 'commit', '-am', 'feat: a'], 'feat: a'),
        # Multiple -m flags become paragraphs, the way git joins them.
        (
            ['git', 'commit', '-m', 'feat: a', '-m', 'body'],
            'feat: a\n\nbody',
        ),
        # Flags after `--` are pathspecs, not messages.
        (['git', 'commit', '-m', 'feat: a', '--', '-m'], 'feat: a'),
        # Nothing recoverable => defer to the real commit-msg hook.
        (['git', 'commit'], None),
        (['git', 'commit', '--amend'], None),
        (['git', 'commit', '-e', '-m', 'feat: a'], None),
        (['git', 'commit', '-F', '-'], None),
    ],
)
def test_message_from_argv(argv: list[str], expected: str | None) -> None:
    assert message_from_argv(argv) == expected


def test_message_from_file(tmp_path: Path) -> None:
    msg = tmp_path / 'msg.txt'
    msg.write_text('feat: from a file')
    argv = ['git', 'commit', '-F', str(msg)]
    assert message_from_argv(argv) == 'feat: from a file'


def test_missing_file_defers(tmp_path: Path) -> None:
    argv = ['git', 'commit', '-F', str(tmp_path / 'nope.txt')]
    assert message_from_argv(argv) is None


@pytest.mark.parametrize('flag', ['-m', '--message', '-F'])
def test_dangling_flag_is_not_a_crash(flag: str) -> None:
    """A trailing flag with no value must not IndexError."""
    assert message_from_argv(['git', 'commit', flag]) is None
