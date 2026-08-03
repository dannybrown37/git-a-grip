"""Tests for the README file-tree hook."""

from __future__ import annotations

from typing import TYPE_CHECKING

from git_a_grip import readme_tree

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

PATHS = [
    'README.md',
    'src/pkg/__init__.py',
    'src/pkg/core.py',
    'tests/test_core.py',
]


def test_build_tree_puts_directories_first() -> None:
    tree = readme_tree.build_tree(PATHS, 'proj')

    assert tree.splitlines() == [
        'proj/',
        '|-- src/',
        '|   `-- pkg/',
        '|       |-- __init__.py',
        '|       `-- core.py',
        '|-- tests/',
        '|   `-- test_core.py',
        '`-- README.md',
    ]


def test_depth_prunes_deep_paths() -> None:
    tree = readme_tree.build_tree(PATHS, 'proj', depth=1)

    assert tree.splitlines() == ['proj/', '`-- README.md']


def test_replace_block_fills_between_markers() -> None:
    text = 'intro\n\n<!-- tree:start -->\nstale\n<!-- tree:end -->\n\nrest\n'

    updated, error = readme_tree.replace_block(text, 'tree', 'proj/')

    assert error == ''
    assert 'stale' not in updated
    assert '```\nproj/\n```' in updated
    assert updated.startswith('intro\n')
    assert updated.endswith('\n\nrest\n')


def test_replace_block_is_idempotent() -> None:
    text = 'a\n<!-- tree:start -->\n<!-- tree:end -->\n'

    once, _ = readme_tree.replace_block(text, 'tree', 'proj/')
    twice, _ = readme_tree.replace_block(once, 'tree', 'proj/')

    assert once == twice


def test_missing_marker_is_an_error_not_a_crash() -> None:
    updated, error = readme_tree.replace_block('nothing here\n', 'tree', 'x')

    assert updated == 'nothing here\n'
    assert 'start' in error


def test_unterminated_block_is_an_error() -> None:
    text = 'a\n<!-- tree:start -->\nb\n'

    _, error = readme_tree.replace_block(text, 'tree', 'x')

    assert 'end' in error


def _sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the hook at a fake repo, with git stubbed out."""
    monkeypatch.setattr(readme_tree, 'repo_root', lambda: tmp_path)
    monkeypatch.setattr(readme_tree, 'tracked_files', lambda: PATHS)
    monkeypatch.setattr(readme_tree.restage, 'add', lambda _paths: 0)


def test_main_reports_a_missing_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sandbox(tmp_path, monkeypatch)

    assert readme_tree.main(['--file=NOPE.md']) == 1


def test_main_fills_the_block_and_then_leaves_it_alone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sandbox(tmp_path, monkeypatch)
    readme = tmp_path / 'README.md'
    readme.write_text('# proj\n\n<!-- tree:start -->\n<!-- tree:end -->\n')

    assert readme_tree.main([]) == 0
    assert 'core.py' in readme.read_text()

    before = readme.read_text()
    assert readme_tree.main([]) == 0
    assert readme.read_text() == before


def test_markers_inside_a_code_fence_are_examples_not_slots() -> None:
    text = (
        'docs:\n\n'
        '```markdown\n<!-- tree:start -->\n<!-- tree:end -->\n```\n\n'
        'the real one:\n\n'
        '<!-- tree:start -->\n<!-- tree:end -->\n'
    )

    updated, error = readme_tree.replace_block(text, 'tree', 'proj/')

    assert error == ''
    # The example survives verbatim; only the slot after it is filled.
    example = '```markdown\n<!-- tree:start -->\n<!-- tree:end -->\n```'
    assert example in updated
    assert updated.count('proj/') == 1
    assert updated.index('proj/') > updated.index('the real one')
