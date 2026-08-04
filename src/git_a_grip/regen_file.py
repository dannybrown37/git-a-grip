"""Run a generator script, and re-stage the files it rewrote.

Every repo that generates a file from its own source ends up with the same
line in `.pre-commit-config.yaml`:

    entry: bash -c 'python scripts/update_readme.py && git add README.md'

It works, and it is wrong in the small ways a wrapper always is: it needs a
shell on the machine, the `git add` is unconditional so the file lands in the
index even on the commits where nothing moved, and a failure in the middle of
the pipeline is whatever bash decided it was.

`embed-command` does not cover this. That hook owns the region between two
markers and writes it itself; these scripts own the whole file and write it
themselves. The difference is who holds the pen, and it is not one flag apart.

    - id: regen-file
      args: ['--command=uv run python scripts/update_readme.py',
             '--file=README.md']

Same contract as `embed-command`, for the same reason: the command comes from
the config and nowhere else, and it is run without a shell. Scanning the tree
for generators to run would make a commit execute whatever a branch added to
`scripts/`.

Naming the output files rather than diffing the tree is deliberate too. A
generator that quietly stops writing its file is the drift this package
exists to catch, so a `--file` that does not exist when the command finishes
fails the commit instead of passing an empty run off as a clean one.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

from git_a_grip import doc_block, restage


def _flags(args: list[str], name: str) -> list[str]:
    """Read every `--name=value` out of a hook's argv, in order.

    `doc_block.flag` returns the first match, which is what a hook with one
    target wants. This one is repeatable: a script that rewrites two files
    should not need two hook entries running it twice.
    """
    prefix = f'--{name}='
    return [a[len(prefix) :] for a in args if a.startswith(prefix)]


def run(command: str, cwd: str) -> str:
    """Run `command` in `cwd`, returning the error to report, if any.

    Output is inherited rather than captured: nothing here embeds it, and a
    slow generator that prints progress should be able to say so while the
    commit waits on it.
    """
    try:
        argv = shlex.split(command)
    except ValueError as exc:  # unbalanced quoting in the config
        return f'cannot parse --command: {exc}'
    if not argv:
        return 'empty --command'

    try:
        result = subprocess.run(argv, check=False, cwd=cwd)  # noqa: S603
    except OSError as exc:
        return f'cannot run {argv[0]}: {exc}'

    if result.returncode != 0:
        return f'`{command}` exited {result.returncode}'
    return ''


def main(argv: list[str]) -> int:
    """Run the configured generator, re-staging the files that changed."""
    root = doc_block.repo_root()
    command = doc_block.flag(argv, 'command', '')
    names = _flags(argv, 'file')

    if not command or not names:
        sys.stderr.write(
            'regen-file: needs both --command and at least one --file. This '
            'hook runs the command you name and re-stages the files you '
            "name, and nothing else:\n  args: ['--command=uv run python "
            "scripts/update_readme.py', '--file=README.md']\n",
        )
        return 1

    paths = [str(root / name) for name in names]
    before = restage.digests(paths)

    error = run(command, str(root))
    if error:
        sys.stderr.write(f'regen-file: {error}\n')
        return 1

    missing = [
        name
        for name, path in zip(names, paths, strict=True)
        if not Path(path).is_file()
    ]
    if missing:
        sys.stderr.write(
            f'regen-file: `{command}` exited 0 but did not write '
            f'{", ".join(missing)}. Either the generator stopped writing it '
            'or the --file path is out of date.\n',
        )
        return 1

    # Exits 0 either way: by the time this returns the regenerated file is
    # already staged, so the commit in flight carries it and failing would
    # only make the author run the same command twice.
    written = restage.changed(before, restage.digests(paths))
    if written:
        sys.stderr.write(
            f'regen-file: rewrote and re-staged {len(written)} file(s):\n'
            + ''.join(f'  {p}\n' for p in written),
        )
        if restage.add(written) != 0:
            sys.stderr.write(
                'regen-file: failed to re-stage the rewritten files.\n',
            )
            return 1
    return 0
