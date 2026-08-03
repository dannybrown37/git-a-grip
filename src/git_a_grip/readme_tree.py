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
commit that updated the tree.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from git_a_grip import restage

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


def markers(marker: str) -> tuple[str, str]:
    """Return the opening and closing comment markers for a block."""
    return f'<!-- {marker}:start -->', f'<!-- {marker}:end -->'


def _marker_line(lines: list[str], needle: str, start_at: int = 0) -> int:
    """Index of the line holding `needle` outside a fenced code block.

    A README that documents this hook contains the markers twice: once as
    the real slot and once inside a ``` fence showing a reader what to
    write. Filling the example instead of the slot is exactly the bug this
    avoids -- and the rule generalises, since a marker inside a fence is
    always illustration, never a slot.
    """
    fenced = False
    for index in range(start_at, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith('```'):
            fenced = not fenced
            continue
        if not fenced and stripped == needle:
            return index
    return -1


def replace_block(text: str, marker: str, body: str) -> tuple[str, str]:
    """Put `body` between the markers, returning the text and any error."""
    start, end = markers(marker)
    lines = text.splitlines()
    first = _marker_line(lines, start)
    if first < 0:
        return text, f'no {start} marker found'
    last = _marker_line(lines, end, first + 1)
    if last < 0:
        return text, f'no {end} marker found'
    block = [start, '', '```', *body.splitlines(), '```', '', end]
    updated = '\n'.join([*lines[:first], *block, *lines[last + 1 :]])
    return (updated + '\n' if text.endswith('\n') else updated), ''


def _flag(args: list[str], name: str, fallback: str) -> str:
    prefix = f'--{name}='
    for arg in args:
        if arg.startswith(prefix):
            return arg[len(prefix) :]
    return fallback


def repo_root() -> Path:
    """Return the top of the working tree, falling back to the cwd."""
    top = subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return Path(top) if top else Path.cwd()


def main(argv: list[str]) -> int:
    """Regenerate the tree block, re-staging the file if it changed."""
    root = repo_root()
    target = root / _flag(argv, 'file', DEFAULT_FILE)
    marker = _flag(argv, 'marker', DEFAULT_MARKER)
    depth = int(_flag(argv, 'depth', str(DEFAULT_DEPTH)))
    if not target.is_file():
        sys.stderr.write(f'readme-tree: {target} does not exist.\n')
        return 1

    original = target.read_text(encoding='utf-8')
    tree = build_tree(tracked_files(), root.name, depth)
    updated, error = replace_block(original, marker, tree)
    if error:
        start, end = markers(marker)
        sys.stderr.write(
            f'readme-tree: {error} in {target.name}. Add\n'
            f'  {start}\n  {end}\n'
            'where the tree should go, or drop this hook.\n',
        )
        return 1
    if updated == original:
        return 0

    target.write_text(updated, encoding='utf-8')
    relative = str(target.relative_to(root))
    sys.stderr.write(f'readme-tree: rewrote and re-staged {relative}\n')
    return 1 if restage.add([str(target)]) != 0 else 0
