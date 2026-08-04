"""ESLint and tsc hooks that avoid the two traps every repo hits.

Both hooks run through the project's own package manager, not through a copy
of the tool that pre-commit installed -- a JS project's lint rules live in its
`node_modules`, and a second, isolated eslint would resolve none of its
plugins. The runner is detected from the lockfile (`pnpm`, `yarn`, `bun`, else
`npx`) and overridable with `--runner=...`.

They run from the repo root unless `--dir=` names a subdirectory. A monorepo
that keeps its JS under `web/` resolves `eslint.config.mjs`, `tsconfig.json`
and `node_modules` from *there*, so running from the root finds none of them
-- which left such a repo writing the `bash -c 'cd web && ...'` wrapper these
hooks exist to replace.

The traps:

**eslint** exits 0 on warnings. A rule set with warnings in it therefore
passes the hook forever, and the warnings accumulate until nobody reads
them. `--max-warnings=0` is the default here; pass `--max-warnings=N` to
loosen it deliberately. Fixable problems are fixed and re-staged, as with
ruff.

**tsc** ignores `tsconfig.json` entirely when it is given file arguments --
so the obvious `entry: tsc --noEmit` hook with `pass_filenames` left on
type-checks with default compiler options, silently, and reports errors that
your real config excludes (or misses ones it includes). This hook never
passes filenames: it type-checks the project, which is the only thing tsc
can correctly do.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from git_a_grip import restage

_RUNNER_FLAG = '--runner='
_DIR_FLAG = '--dir='
# Lockfile -> the command that runs a binary from that project's deps.
_LOCKFILES = (
    ('pnpm-lock.yaml', 'pnpm exec'),
    ('bun.lockb', 'bun x'),
    ('yarn.lock', 'yarn'),
    ('package-lock.json', 'npx --no-install'),
)
DEFAULT_RUNNER = 'npx --no-install'
# pre-commit exports these for its own hook env; a node tool does not want
# them, and a repo whose scripts shell out to python very much does not.
_INHERITED_ENV_VARS = ('VIRTUAL_ENV', 'PYTHONHOME', 'PYTHONPATH')


def repo_root() -> Path:
    """Return the top of the working tree, falling back to the cwd."""
    top = subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return Path(top) if top else Path.cwd()


def take_dir(argv: list[str], root: Path) -> tuple[Path, list[str]]:
    """Pull `--dir=` out of argv, returning where the tool should run."""
    workdir = root
    rest: list[str] = []
    for arg in argv:
        if arg.startswith(_DIR_FLAG):
            workdir = root / arg[len(_DIR_FLAG) :]
        else:
            rest.append(arg)
    return workdir, rest


def detect_runner(start: Path, root: Path | None = None) -> str:
    """Pick the package manager to run a local binary through.

    Searched from `start` upward to the repo root, because a workspace keeps
    one lockfile at the top even when the package being linted is a
    subdirectory. The nearest lockfile wins: a subdirectory with its own
    lockfile is its own project and knows better than the root does.
    """
    stop = root or start
    for current in (start, *start.parents):
        for lockfile, runner in _LOCKFILES:
            if (current / lockfile).is_file():
                return runner
        if current == stop:
            break
    return DEFAULT_RUNNER


def split_args(
    argv: list[str],
    workdir: Path,
    root: Path | None = None,
) -> tuple[list[str], list[str]]:
    """Split argv into the runner command and the arguments for the tool."""
    runner = ''
    rest: list[str] = []
    for arg in argv:
        if arg.startswith(_RUNNER_FLAG):
            runner = arg[len(_RUNNER_FLAG) :]
        else:
            rest.append(arg)
    return (runner or detect_runner(workdir, root)).split(), rest


def within(path: str, workdir: Path) -> bool:
    """Is `path` inside `workdir`?"""
    try:
        Path(path).resolve().relative_to(workdir.resolve())
    except ValueError:
        return False
    return True


def relocate(
    args: list[str],
    paths: list[str],
    workdir: Path,
) -> tuple[list[str], list[str]]:
    """Re-express the file arguments relative to `workdir`.

    pre-commit names files from the repo root, but the tool is about to run
    from `workdir`, where `web/app/page.tsx` resolves to nothing. Files
    outside `workdir` are dropped rather than passed as `../scraper/x.ts`:
    they are covered by no config the tool is about to load, so the only
    thing sending them along produces is a confusing error.

    Returns the rewritten argv and the surviving paths, the latter still
    named from the repo root so `restage` can find them.
    """
    files = set(paths)
    kept_args: list[str] = []
    for arg in args:
        if arg not in files:
            kept_args.append(arg)
        elif within(arg, workdir):
            relative = Path(arg).resolve().relative_to(workdir.resolve())
            kept_args.append(str(relative))
    return kept_args, [p for p in paths if within(p, workdir)]


def clean_env() -> dict[str, str]:
    """Return the environment minus pre-commit's own venv pointers."""
    env = dict(os.environ)
    for name in _INHERITED_ENV_VARS:
        env.pop(name, None)
    return env


def run(command: list[str], workdir: Path, tool: str) -> int:
    """Run `command` from `workdir`, or explain why it could not."""
    try:
        return subprocess.run(  # noqa: S603
            command,
            cwd=workdir,
            env=clean_env(),
            check=False,
        ).returncode
    except FileNotFoundError:
        sys.stderr.write(
            f'{tool}: cannot run {command[0]!r} -- it is not on PATH. '
            f'Install it, or set args: ["--runner=<command>", ...].\n',
        )
        return 1


def eslint(argv: list[str]) -> int:
    """Lint and fix with the project's eslint, re-staging what it rewrote."""
    root = repo_root()
    workdir, argv = take_dir(argv, root)
    runner, args = split_args(argv, workdir, root)
    if not any(a.startswith('--max-warnings') for a in args):
        args = ['--max-warnings=0', *args]
    paths = restage.target_paths(args)
    if workdir != root:
        args, paths = relocate(args, paths, workdir)
    if not paths:
        return 0  # pre-commit passed only files eslint has nothing to say on
    before = restage.digests(paths)
    code = run([*runner, 'eslint', '--fix', *args], workdir, 'eslint')
    fixed = restage.changed(before, restage.digests(paths))
    if fixed:
        sys.stderr.write(
            f'eslint: rewrote and re-staged {len(fixed)} file(s):\n'
            + ''.join(f'  {p}\n' for p in fixed),
        )
        if restage.add(fixed) != 0:
            sys.stderr.write('eslint: failed to re-stage the fixed files.\n')
            return 1
    return code


def tsc(argv: list[str]) -> int:
    """Type-check the project -- never individual files. See module docs."""
    root = repo_root()
    workdir, argv = take_dir(argv, root)
    runner, args = split_args(argv, workdir, root)
    named = any(
        arg in {'-p', '--project'} or arg.startswith('--project=')
        for arg in args
    )
    # `.` is workdir, so --dir= already points this at the right tsconfig.
    project = [] if named else ['-p', '.']
    return run([*runner, 'tsc', '--noEmit', *project, *args], workdir, 'tsc')
