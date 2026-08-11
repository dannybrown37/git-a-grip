"""Reaching the *consuming* project's environment, not pre-commit's.

Most hooks here run inside the isolated env pre-commit builds for this
package, which is the right place for a tool that only reads source. It is
the wrong place for a tool that has to resolve the project's own imports:
pytest imports the code under test, and mypy type-checks against the same
dependencies. Neither exists in this package's env, and pre-commit's answer
for that -- `additional_dependencies` -- is a second copy of the project's
requirements, maintained by hand, drifting from the first.

So those hooks shell out through a runner that resolves the project's
environment (`uv run ...` by default), from the repo root rather than
wherever git was invoked.

Dropping pre-commit's venv pointers is the part that is easy to miss and
hard to debug once missed: pre-commit exports VIRTUAL_ENV for the hook env
it built, and a runner that honours it goes looking for the project's
dependencies in an environment holding none of them.
"""

from __future__ import annotations

import os
import subprocess

RUNNER_FLAG = '--runner='
# pre-commit exports these for the isolated env it built for *this* package.
# Leaking them into the runner would shadow the project's own environment.
_INHERITED_ENV_VARS = ('VIRTUAL_ENV', 'PYTHONHOME', 'PYTHONPATH')


def split_runner(argv: list[str], default: str) -> tuple[list[str], list[str]]:
    """Split argv into the runner command and the arguments for the tool.

    The runner is the whole command, not a prefix: `--runner=uv run --group
    typing mypy` names an environment *and* the tool it runs, because the
    two are one decision.
    """
    runner = default
    rest: list[str] = []
    for arg in argv:
        if arg.startswith(RUNNER_FLAG):
            runner = arg[len(RUNNER_FLAG) :]
        else:
            rest.append(arg)
    return runner.split(), rest


def repo_root() -> str:
    """Return the top level of the working tree, or '' if git cannot say."""
    return subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


def clean_env() -> dict[str, str]:
    """Return the environment minus pre-commit's own venv pointers."""
    env = dict(os.environ)
    for name in _INHERITED_ENV_VARS:
        env.pop(name, None)
    return env
