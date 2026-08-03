"""Tests for the README file-tree hook.

The block-filling half moved to `doc_block` and is tested there; what is
left here is the tree, and the wiring that puts one in a file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from git_a_grip import doc_block, embed_tree

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
    tree = embed_tree.build_tree(PATHS, 'proj')

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
    tree = embed_tree.build_tree(PATHS, 'proj', depth=1)

    assert tree.splitlines() == ['proj/', '`-- README.md']


def _sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the hook at a fake repo, with git stubbed out."""
    monkeypatch.setattr(doc_block, 'repo_root', lambda: tmp_path)
    monkeypatch.setattr(embed_tree, 'tracked_files', lambda: PATHS)
    monkeypatch.setattr(doc_block.restage, 'add', lambda _paths: 0)


def test_main_reports_a_missing_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sandbox(tmp_path, monkeypatch)

    assert embed_tree.main(['--file=NOPE.md']) == 1


def test_main_fills_the_block_and_then_leaves_it_alone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sandbox(tmp_path, monkeypatch)
    readme = tmp_path / 'README.md'
    readme.write_text('# proj\n\n<!-- tree:start -->\n<!-- tree:end -->\n')

    assert embed_tree.main([]) == 0
    assert 'core.py' in readme.read_text()

    before = readme.read_text()
    assert embed_tree.main([]) == 0
    assert readme.read_text() == before
