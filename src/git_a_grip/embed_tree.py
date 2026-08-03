"""Keep a file-tree block in the README true, by regenerating it on commit.

Every repo that documents its own layout writes the tree once, by hand, and
then renames a directory. Nobody re-runs `tree`. Six months later the README
describes a structure that no longer exists, which is worse than documenting
nothing -- a reader trusts it.

Mark the block once:

    <!-- tree:start -->
    <!-- tree:end -->

and this hook fills it, in a fenced code block, on every commit that touches
the tracked files. The contents come from `git ls-files`, so the tree shows
exactly what is committed: no `.venv`, no build output, no gitignore rules
re-implemented here and drifted from the real one.

Like the other rewriting hooks, an out-of-date README is fixed and re-staged
rather than merely reported, so the commit that moved the file is also the
commit that updated the tree. Everything about finding and filling the block
lives in `doc_block`; what is here is the tree itself.
"""

from __future__ import annotations

import subprocess

from git_a_grip import doc_block

DEFAULT_FILE = 'README.md'
DEFAULT_MARKER = 'tree'
DEFAULT_DEPTH = 0  # unlimited
_ELBOW, _TEE, _PIPE, _SPACE = '`-- ', '|-- ', '|   ', '    '


def tracked_files() -> list[str]:
    """Return every file git tracks, relative to the repo root."""
    result = subprocess.run(
        ['git', 'ls-files', '-z'],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    return sorted(p for p in result.stdout.split('\0') if p)


def _prune(paths: list[str], depth: int) -> list[str]:
    if depth <= 0:
        return paths
    return [p for p in paths if p.count('/') < depth]


def build_tree(paths: list[str], root: str, depth: int = DEFAULT_DEPTH) -> str:
    """Render `paths` as an indented tree rooted at `root`."""
    tree: dict[str, dict] = {}
    for path in _prune(paths, depth):
        node = tree
        for part in path.split('/'):
            node = node.setdefault(part, {})
    lines = [f'{root}/']
    _render(tree, '', lines)
    return '\n'.join(lines)


def _render(node: dict[str, dict], prefix: str, lines: list[str]) -> None:
    # Directories first, then files, each alphabetically -- the order a
    # reader scans for, and the one `tree` itself uses with --dirsfirst.
    entries = sorted(node.items(), key=lambda kv: (not kv[1], kv[0].lower()))
    for index, (name, children) in enumerate(entries):
        last = index == len(entries) - 1
        suffix = '/' if children else ''
        lines.append(f'{prefix}{_ELBOW if last else _TEE}{name}{suffix}')
        if children:
            _render(children, prefix + (_SPACE if last else _PIPE), lines)


def main(argv: list[str]) -> int:
    """Regenerate the tree block, re-staging the file if it changed."""
    root = doc_block.repo_root()
    target = root / doc_block.flag(argv, 'file', DEFAULT_FILE)
    marker = doc_block.flag(argv, 'marker', DEFAULT_MARKER)
    depth = int(doc_block.flag(argv, 'depth', str(DEFAULT_DEPTH)))
    tree = build_tree(tracked_files(), root.name, depth)
    return doc_block.embed('embed-tree', root, target, marker, tree)
