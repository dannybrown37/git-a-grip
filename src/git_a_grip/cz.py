"""Run commitizen out of this hook's own interpreter.

pre-commit installs this package into an isolated env with commitizen as a
declared dependency, so `sys.executable -m commitizen` always resolves. That
deliberately replaces per-repo invocations like `uv run cz` or
`uvx --from commitizen cz`, which differ by consumer and are the thing most
likely to break when a hook is copied between projects.
"""

from __future__ import annotations

import subprocess
import sys


def run(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke commitizen with `args`, capturing output."""
    return subprocess.run(  # noqa: S603
        [sys.executable, '-m', 'commitizen', *args],
        capture_output=True,
        text=True,
        check=False,
    )
