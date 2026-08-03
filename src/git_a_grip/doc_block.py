"""The half of a doc-embedding hook that has nothing to do with the content.

Two hooks now keep a generated block inside a checked-in file: `embed-tree`
writes a file tree, `embed-command` writes the output of a command. What they
share is everything except the body -- finding the markers, refusing to fill
an example inside a code fence, writing only on a real change, re-staging so
the fix lands in the commit that caused it.

That sharing is not a tidiness argument. `_marker_line` skips fenced blocks
because a README documenting these hooks holds the markers twice, and the
subtle half of the rule is the half a second copy would get wrong. One copy,
two callers.

A generator supplies `body`; this module does the rest.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from git_a_grip import restage


def markers(marker: str) -> tuple[str, str]:
    """Return the opening and closing comment markers for a block."""
    return f'<!-- {marker}:start -->', f'<!-- {marker}:end -->'


def _marker_line(lines: list[str], needle: str, start_at: int = 0) -> int:
    """Index of the line holding `needle` outside a fenced code block.

    A README that documents these hooks contains the markers twice: once as
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


def flag(args: list[str], name: str, fallback: str) -> str:
    """Read `--name=value` out of a hook's argv, or return `fallback`."""
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


def embed(tool: str, root: Path, target: Path, marker: str, body: str) -> int:
    """Write `body` into `target`'s block, re-staging it if it changed.

    A rewrite still exits 0: the fix is staged by the time this returns, so
    the commit in flight already carries it and failing would only make the
    author run the same command twice. Non-zero is for the cases nothing can
    fix on its own -- no such file, no markers, a `git add` that failed.
    """
    if not target.is_file():
        sys.stderr.write(f'{tool}: {target} does not exist.\n')
        return 1

    original = target.read_text(encoding='utf-8')
    updated, error = replace_block(original, marker, body)
    if error:
        start, end = markers(marker)
        sys.stderr.write(
            f'{tool}: {error} in {target.name}. Add\n'
            f'  {start}\n  {end}\n'
            'where the block should go, or drop this hook.\n',
        )
        return 1
    if updated == original:
        return 0

    target.write_text(updated, encoding='utf-8')
    relative = str(target.relative_to(root))
    sys.stderr.write(f'{tool}: rewrote and re-staged {relative}\n')
    return 1 if restage.add([str(target)]) != 0 else 0
