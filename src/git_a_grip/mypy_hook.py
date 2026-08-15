"""Type-check the project with mypy, from the project's own environment.

Two hooks here already carry half of this one's argument, and mypy is where
both halves apply at once.

`pytest` runs through `uv run` because a test suite imports the project, so
it needs the project's dependencies. A type checker needs them for the same
reason and fails worse without them: mypy that cannot resolve an import
reports errors about the import rather than about your code, and the usual
cure for that noise -- `ignore_missing_imports` -- turns every symbol from
that package into `Any`, so the mistakes it was installed to catch quietly
stop being reported. Running it from pre-commit's own env means keeping a
copy of your requirements in `additional_dependencies`, and the day that
copy drifts the hook goes green for the wrong reason.

`tsc` never passes filenames, because tsc given files ignores tsconfig.json.
mypy given files still reads its config, but it answers a narrower question:
it checks what it was handed plus whatever that imports, so a module nothing
in this commit reaches is not checked at all. The error you introduce today
then surfaces on whichever future commit happens to touch a file that
imports it -- a hook whose answer depends on what you touched is not a type
check.

So this hook passes no targets of its own. `mypy` with no files takes them
from `files`, `packages` or `modules` in your mypy config, which means the
hook checks precisely what you check when you type `mypy` yourself: one
answer, in the terminal and in the commit. Name targets in `args` instead if
you prefer, and accept that the two can then disagree.

    - id: mypy

    - id: mypy
      args: ['--runner=uv run --group typing mypy']

The default runner installs mypy itself, with `uv run --with mypy`, so that
the first form above is the whole configuration: nothing to declare, nothing
to keep in step. `--with` is the one way to have both halves at once --
`uv run mypy` resolves the project's dependencies but requires the project
to have declared a type checker it never imports, and `additional_dependencies`
installs the tool but not the dependencies it has to resolve. A project that
does declare mypy is unaffected; uv resolves the two requirements together
and a pin in the project wins.

Nothing here is mypy-specific beyond the name and the default runner: point
`--runner=` at `uv run --with pyright pyright` or `uv run ty check` and the
same reasoning holds.
"""

from __future__ import annotations

import subprocess
import sys

from git_a_grip.project_env import clean_env, repo_root, split_runner

DEFAULT_RUNNER = 'uv run --with mypy mypy'
# mypy's own exit code for "I was called wrongly", as against 1 for "I found
# type errors". Only the former is worth explaining -- and `uv` exits 2 for
# its own usage errors too, which is why the hint below refuses to claim
# mypy is the one that complained.
USAGE_EXIT = 2
# The flags that name something to check without looking like a path.
_TARGET_FLAGS = ('-m', '--module', '-p', '--package', '-c', '--command')


def names_a_target(args: list[str]) -> bool:
    """Whether `args` already tells mypy what to check.

    A flag *value* that is not itself a flag counts as a target here
    (`--config-file mypy.ini` reads as one). The cost of that is a hint we
    would otherwise have printed, never a change in what runs.
    """
    return any(
        not arg.startswith('-')
        or arg in _TARGET_FLAGS
        or arg.startswith(tuple(f'{flag}=' for flag in _TARGET_FLAGS))
        for arg in args
    )


def _no_target_hint() -> str:
    # Deliberately conditional. The runner shares this exit code -- `uv run
    # --group typing mypy` against an undeclared group exits 2 before mypy
    # starts -- and a hint that asserts mypy ran sends you to edit the mypy
    # config over an error in the pre-commit one.
    return (
        'mypy: exited 2. Read the error above first: if it came from the '
        'runner (an undeclared dependency group, an unknown flag) then fix '
        'that -- the exit code is shared and this hook cannot tell which of '
        'the two spoke.\n'
        'If it was mypy, nothing was named to check. This hook passes no '
        'targets of its own, so that it checks what `mypy` checks when you '
        'run it by hand. Name them once, in your mypy config:\n'
        '  [tool.mypy]\n'
        '  files = ["src", "tests"]\n'
        'or, to keep them in the hook alone, args: [src, tests].\n'
    )


def main(argv: list[str]) -> int:
    """Type-check the project, returning mypy's own exit code."""
    runner, args = split_runner(argv, DEFAULT_RUNNER)
    if not runner:
        sys.stderr.write('mypy: --runner is empty, nothing to run.\n')
        return 1
    try:
        code = subprocess.run(  # noqa: S603
            [*runner, *args],
            cwd=repo_root() or None,
            env=clean_env(),
            check=False,
        ).returncode
    except FileNotFoundError:
        sys.stderr.write(
            f'mypy: cannot run {runner[0]!r} -- it is not on PATH. '
            f'Install it, or set args: ["--runner=<command>", ...].\n',
        )
        return 1

    if code == USAGE_EXIT and not names_a_target(args):
        sys.stderr.write(_no_target_hint())
    return code
