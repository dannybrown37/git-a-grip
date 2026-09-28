"""Lint shell scripts with shellcheck.

Shell is the code in a repo that most often has no linter at all, and it is
where the quiet failures live: an unquoted `$var` that splits on the one path
with a space in it, a `cd` without `|| exit` that runs the rest of the script
in the wrong directory. shellcheck catches both, and `shellcheck-py` ships it
as a binary wheel, so it comes in through `additional_dependencies` and a
consuming repo needs nothing on PATH.

Unlike the other hooks here, this one never rewrites anything, so there is
nothing to re-stage. shellcheck can print its suggestions as a diff, but
applying them unasked is a bigger thing than formatting -- a changed quote
can change what a script does -- so that stays a human's decision. The
formatting half of the job belongs to a formatter.

Filenames are passed, as with zizmor: shellcheck has no project config that
decides what to check, so the list pre-commit computed from `types: [shell]`
-- which reads the shebang of an executable file, so an extensionless
`bin/deploy` is included once it is `chmod +x` -- is the right one. Its
exit code passes through untouched.

    - id: shellcheck

    - id: shellcheck
      args: [--severity=warning]
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from git_a_grip import restage


def shellcheck_path() -> str | None:
    """Locate the shellcheck binary, preferring this interpreter's own env.

    Looking beside the interpreter first is what pins the hook to the copy
    pre-commit installed for it, where the machine may have an older
    shellcheck from its package manager on PATH.
    """
    local = Path(sys.executable).parent / 'shellcheck'
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    return shutil.which('shellcheck')


def main(argv: list[str]) -> int:
    """Lint the given scripts, returning shellcheck's own exit code."""
    binary = shellcheck_path()
    if binary is None:
        sys.stderr.write(
            'shellcheck: not installed in this hook env and not on PATH. '
            'pre-commit installs it from `additional_dependencies`; if you '
            'overrode that, put `shellcheck-py` back in it.\n',
        )
        return 1

    if not restage.target_paths(argv):
        # shellcheck given no files exits 3 with its usage -- a failed
        # commit for a hook that had nothing to lint.
        return 0

    return subprocess.run([binary, *argv], check=False).returncode  # noqa: S603
