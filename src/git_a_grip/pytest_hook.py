"""Run the consuming repo's test suite as a hook, from the repo root.

Unlike the other hooks here, this one deliberately does *not* run inside the
env pre-commit built for this package: a test suite needs the consuming
project's own dependencies, which that isolated env will never have. So it
shells out to a runner that resolves the project's environment -- `uv run
pytest` by default -- and everything after the runner flags is handed
straight to pytest:

    - id: pytest
      args: [tests/, -q]

    - id: pytest
      args: ['--runner=uv run --extra api pytest', tests/, -q]

Two details that a hand-rolled `entry:` usually gets wrong: it runs from the
repo root rather than wherever git was invoked, and it drops the VIRTUAL_ENV
that pre-commit exports for its own hook env, which would otherwise point the
runner at an environment holding none of the project's dependencies. Both
live in `project_env`, which the `mypy` hook needs for the same reasons.
"""

from __future__ import annotations

import subprocess
import sys

from git_a_grip.project_env import clean_env, repo_root, split_runner

DEFAULT_RUNNER = 'uv run pytest'


def split_args(argv: list[str]) -> tuple[list[str], list[str]]:
    """Split argv into the runner command and the arguments for pytest."""
    return split_runner(argv, DEFAULT_RUNNER)


def main(argv: list[str]) -> int:
    """Run the project's test suite, returning the runner's exit code."""
    runner, pytest_args = split_args(argv)
    if not runner:
        sys.stderr.write('pytest: --runner is empty, nothing to run.\n')
        return 1
    try:
        return subprocess.run(  # noqa: S603
            [*runner, *pytest_args],
            cwd=repo_root() or None,
            env=clean_env(),
            check=False,
        ).returncode
    except FileNotFoundError:
        sys.stderr.write(
            f'pytest: cannot run {runner[0]!r} -- it is not on PATH. '
            f'Install it, or set args: ["--runner=<command>", ...].\n',
        )
        return 1
