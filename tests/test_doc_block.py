"""Tests for the block-filling machinery both embed hooks run on."""

from __future__ import annotations

from typing import TYPE_CHECKING

from git_a_grip import doc_block

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_replace_block_fills_between_markers() -> None:
    text = 'intro\n\n<!-- tree:start -->\nstale\n<!-- tree:end -->\n\nrest\n'

    updated, error = doc_block.replace_block(text, 'tree', 'proj/')

    assert error == ''
    assert 'stale' not in updated
    assert '```\nproj/\n```' in updated
    assert updated.startswith('intro\n')
    assert updated.endswith('\n\nrest\n')


def test_replace_block_is_idempotent() -> None:
    text = 'a\n<!-- tree:start -->\n<!-- tree:end -->\n'

    once, _ = doc_block.replace_block(text, 'tree', 'proj/')
    twice, _ = doc_block.replace_block(once, 'tree', 'proj/')

    assert once == twice


def test_missing_marker_is_an_error_not_a_crash() -> None:
    updated, error = doc_block.replace_block('nothing here\n', 'tree', 'x')

    assert updated == 'nothing here\n'
    assert 'start' in error


def test_unterminated_block_is_an_error() -> None:
    text = 'a\n<!-- tree:start -->\nb\n'

    _, error = doc_block.replace_block(text, 'tree', 'x')

    assert 'end' in error


def test_markers_inside_a_code_fence_are_examples_not_slots() -> None:
    text = (
        'docs:\n\n'
        '```markdown\n<!-- tree:start -->\n<!-- tree:end -->\n```\n\n'
        'the real one:\n\n'
        '<!-- tree:start -->\n<!-- tree:end -->\n'
    )

    updated, error = doc_block.replace_block(text, 'tree', 'proj/')

    assert error == ''
    # The example survives verbatim; only the slot after it is filled.
    example = '```markdown\n<!-- tree:start -->\n<!-- tree:end -->\n```'
    assert example in updated
    assert updated.count('proj/') == 1
    assert updated.index('proj/') > updated.index('the real one')


def test_each_marker_name_owns_its_own_block() -> None:
    # Two embed hooks on one README is the point of --marker; filling one
    # block must leave the other alone.
    text = (
        '<!-- help:start -->\n<!-- help:end -->\n'
        '<!-- tree:start -->\nkeep me\n<!-- tree:end -->\n'
    )

    updated, error = doc_block.replace_block(text, 'help', 'usage: x')

    assert error == ''
    assert 'usage: x' in updated
    assert 'keep me' in updated


def test_flag_reads_a_value_or_falls_back() -> None:
    assert doc_block.flag(['--file=X.md'], 'file', 'README.md') == 'X.md'
    assert doc_block.flag([], 'file', 'README.md') == 'README.md'
    # A value holding the separator survives whole: --command=a --help.
    assert doc_block.flag(['--command=a -b=c'], 'command', '') == 'a -b=c'


def test_embed_restages_only_when_the_file_changed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staged: list[list[str]] = []

    def fake_add(paths: list[str]) -> int:
        staged.append(paths)
        return 0

    monkeypatch.setattr(doc_block.restage, 'add', fake_add)
    target = tmp_path / 'README.md'
    target.write_text('<!-- x:start -->\n<!-- x:end -->\n')

    assert doc_block.embed('t', tmp_path, target, 'x', 'body') == 0
    assert len(staged) == 1

    assert doc_block.embed('t', tmp_path, target, 'x', 'body') == 0
    assert len(staged) == 1


def test_embed_reports_a_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / 'NOPE.md'

    assert doc_block.embed('t', tmp_path, missing, 'x', 'body') == 1
