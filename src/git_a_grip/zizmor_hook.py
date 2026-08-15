"""Audit GitHub Actions workflows with zizmor, keeping its fixes staged.

The same bargain as the ruff hooks, for the other half of a repo that nobody
lints: `.github/workflows/*.yml` is code with credentials in it, and the
mistakes it invites -- a `pull_request_target` that checks out the PR head,
a `${{ github.event.* }}` interpolated into a `run:` block -- are not the
kind a reviewer reliably catches by eye. zizmor is the static analyser for
them, and it is a self-contained binary wheel, so it comes in through
`additional_dependencies` and a consuming repo needs nothing on PATH.

Two decisions are worth stating, because both could reasonably have gone the
other way:

**Filenames are passed.** Unlike `mypy` and `tsc`, zizmor has no project
config that decides what to check -- it audits what it is handed -- so the
list pre-commit already computed is the right one, and auditing every
workflow on a commit that touched one is a cost with nothing to show for it.
The `files:` pattern in `.pre-commit-hooks.yaml` is what keeps that list to
workflows and action definitions; widen it there, not here.

**Fixes are re-staged, but never requested.** `--fix` is zizmor's own flag
and stays the caller's choice: rewriting a workflow is a bigger thing than
reformatting a line, and this hook will not decide that for a repo. But a
repo that *does* ask for it gets the package's usual contract -- the rewrite
is staged, so it is part of the commit rather than left dirty behind a
failure. The digest comparison costs nothing when no fix was asked for.

zizmor's exit code passes through untouched: 14 means it found something,
and that is the hook failing for the reason it exists.

    - id: zizmor

    - id: zizmor
      args: [--min-severity=medium]

    - id: zizmor
      args: [--fix, --persona=pedantic]

Online audits need a token (`GH_TOKEN`), which a commit hook has no business
demanding; zizmor runs offline by default and says so, and the environment
is passed through untouched for the repos that do export one.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from git_a_grip import restage


def zizmor_path() -> str | None:
    """Locate the zizmor binary, preferring this interpreter's own env.

    zizmor ships as a compiled executable rather than an importable module,
    so `sys.executable -m zizmor` -- what the ruff hooks do -- is not
    available. Looking next to the interpreter first is what makes the hook
    find the copy pre-commit installed for it, in a run where some *other*
    zizmor is also on PATH.
    """
    local = Path(sys.executable).parent / 'zizmor'
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    return shutil.which('zizmor')


def main(argv: list[str]) -> int:
    """Audit the given workflows, returning zizmor's own exit code."""
    binary = zizmor_path()
    if binary is None:
        sys.stderr.write(
            'zizmor: not installed in this hook env and not on PATH. '
            'pre-commit installs it from `additional_dependencies`; if you '
            'overrode that, put `zizmor` back in it.\n',
        )
        return 1

    paths = restage.target_paths(argv)
    if not paths:
        # pass_filenames is on, so an empty list means every candidate file
        # was filtered out. zizmor given no input exits 2 with its usage --
        # a failed commit for a hook that had nothing to do.
        return 0

    before = restage.digests(paths)
    code = subprocess.run([binary, *argv], check=False).returncode  # noqa: S603
    fixed = restage.changed(before, restage.digests(paths))
    if fixed:
        sys.stderr.write(
            f'zizmor: rewrote and re-staged {len(fixed)} file(s):\n'
            + ''.join(f'  {p}\n' for p in fixed),
        )
        if restage.add(fixed) != 0:
            sys.stderr.write('zizmor: failed to re-stage the fixed files.\n')
            return 1
    return code
