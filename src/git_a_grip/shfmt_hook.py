"""Format shell scripts with shfmt, keeping the rewrite staged.

The formatting half of the shell pair, as `ruff-format` is to `ruff-check`:
shellcheck says what is wrong and never touches the file, shfmt touches the
file and never argues about meaning. `shfmt-py` ships the binary as a wheel,
so it comes in through `additional_dependencies` and a consuming repo needs
nothing on PATH.

`-w` is always passed. Without it shfmt prints the formatted script to
stdout and leaves the file alone -- a hook that passes having fixed nothing.
Everything else in `args` reaches shfmt after it, in order. Pass no style
flags and shfmt reads the repo's `.editorconfig` instead, which is the place
a shell style belongs when an editor should agree with the hook:

    - id: shfmt

    - id: shfmt
      args: [-i, '2', -ci]

The rewrite is re-staged and the hook exits 0, like every formatter here.
Non-zero is left for the one thing shfmt cannot fix: a script it cannot
parse.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from git_a_grip import restage


def shfmt_path() -> str | None:
    """Locate the shfmt binary, preferring this interpreter's own env.

    Looking beside the interpreter first is what pins the hook to the copy
    pre-commit installed for it, rather than a different shfmt version on
    PATH that would format the same script differently.
    """
    local = Path(sys.executable).parent / 'shfmt'
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    return shutil.which('shfmt')


def main(argv: list[str]) -> int:
    """Format the given scripts in place and re-stage what moved."""
    binary = shfmt_path()
    if binary is None:
        sys.stderr.write(
            'shfmt: not installed in this hook env and not on PATH. '
            'pre-commit installs it from `additional_dependencies`; if you '
            'overrode that, put `shfmt-py` back in it.\n',
        )
        return 1

    paths = restage.target_paths(argv)
    if not paths:
        # shfmt given no files formats stdin, which under a git hook can be
        # the terminal -- the commit would sit waiting with no clue why.
        return 0

    before = restage.digests(paths)
    code = subprocess.run([binary, '-w', *argv], check=False).returncode  # noqa: S603
    fixed = restage.changed(before, restage.digests(paths))
    if fixed:
        sys.stderr.write(
            f'shfmt: rewrote and re-staged {len(fixed)} file(s):\n'
            + ''.join(f'  {p}\n' for p in fixed),
        )
        if restage.add(fixed) != 0:
            sys.stderr.write(
                'shfmt: failed to re-stage the rewritten files.\n',
            )
            return 1
    return code
