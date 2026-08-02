"""Re-stage the files a hook rewrote, so its fixes land in the commit.

A formatter that edits the working tree mid-commit leaves the fix *unstaged*:
the commit still records the unformatted content and the next `git status` is
dirty for no reason the human asked for. Every repo that hit this solved it
the same way, with a `bash -c '... && git add "$@"'` wrapper around the entry.

Doing it here instead means the `git add` is narrowed to the files that
actually changed, compared by digest rather than assumed. pre-commit stashes
unstaged changes for the duration of a hook run, so the working tree holds
staged content only and re-adding a changed file cannot smuggle in an edit
the author meant to keep back.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def target_paths(args: list[str]) -> list[str]:
    """Pick the existing file paths out of a hook's argv.

    Flag *values* that name a file (`--config .ruff.toml`) are picked up too,
    which is harmless: a path is only ever re-staged after its digest changes,
    and a config file the tool merely read has not changed.
    """
    return [a for a in args if not a.startswith('-') and Path(a).is_file()]


def digests(paths: list[str]) -> dict[str, str]:
    """Map each readable path to a digest of its current contents."""
    out: dict[str, str] = {}
    for path in paths:
        try:
            out[path] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        except OSError:
            continue
    return out


def changed(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Return the paths whose digest moved between the two snapshots."""
    return sorted(p for p, d in after.items() if before.get(p) != d)


def add(paths: list[str]) -> int:
    """Stage `paths`, returning git's exit code (0 when there is nothing)."""
    if not paths:
        return 0
    return subprocess.run(  # noqa: S603
        ['git', 'add', '--', *paths],  # noqa: S607
        check=False,
    ).returncode
