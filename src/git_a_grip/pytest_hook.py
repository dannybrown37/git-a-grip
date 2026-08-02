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
runner at an environment holding none of the project's dependencies.
"""

from __future__ import annotations

import os
import subprocess
import sys

DEFAULT_RUNNER = 'uv run pytest'
_RUNNER_FLAG = '--runner='
# pre-commit exports these for the isolated env it built for *this* package.
# Leaking them into the runner would shadow the project's own environment.
_INHERITED_ENV_VARS = ('VIRTUAL_ENV', 'PYTHONHOME', 'PYTHONPATH')


def split_args(argv: list[str]) -> tuple[list[str], list[str]]:
    """Split argv into the runner command and the arguments for pytest."""
    runner = DEFAULT_RUNNER
    rest: list[str] = []
    for arg in argv:
        if arg.startswith(_RUNNER_FLAG):
            runner = arg[len(_RUNNER_FLAG) :]
        else:
            rest.append(arg)
    return runner.split(), rest


def repo_root() -> str:
    """Return the top level of the working tree."""
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


def main_cli() -> None:
    """Console-script entry point."""
    raise SystemExit(main(sys.argv[1:]))


if __name__ == '__main__':
    main_cli()
