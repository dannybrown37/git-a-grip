"""Keep a command's output -- `--help`, `make help` -- true in the README.

The usage block in a README is the first thing a reader trusts and the last
thing anybody updates. It is written once, by pasting a terminal, and then a
flag is renamed. Same failure as the hand-written file tree, same fix: mark
the slot, and regenerate it on the commit that changed the command.

    <!-- help:start -->
    <!-- help:end -->

    - id: embed-command
      args: ['--marker=help', '--command=uv run gag --help']
      files: ^(src/.*\\.py|README\\.md)$

The command is named in the config and nowhere else. Discovering executables
in the tree and running each with `--help` would be the obvious convenience
and is not on offer: it makes a commit hook execute whatever a branch happens
to have added to `bin/`. One command, written down by the person who wants it
run.

Two blocks means two hook entries, each with its own `--marker`. That is
verbose in a way a config file of its own would not be, and it keeps every
answer to "where does this block come from?" inside `.pre-commit-config.yaml`.

Failure is loud rather than embedded: a command that cannot be found, or that
exits with an unexpected status, aborts the commit with its own stderr. The
alternative is a README that reads `error: no such option` in a code fence,
which is exactly the confident-and-wrong documentation this hook exists to
stop.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys

from git_a_grip import doc_block

DEFAULT_FILE = 'README.md'
DEFAULT_MARKER = 'help'
DEFAULT_EXIT = 0
# A subprocess is not a tty, but tools read more than isatty() -- a
# CLICOLOR_FORCE in the environment, a FORCE_COLOR left over from CI. Escape
# codes in a README are unreadable, so say no in every dialect.
_PLAIN_ENV = {
    'NO_COLOR': '1',
    'TERM': 'dumb',
    'CLICOLOR': '0',
    'CLICOLOR_FORCE': '0',
    'FORCE_COLOR': '0',
    # Wrapping follows the terminal width of whoever last ran the hook, and a
    # block that reflows per-developer is a diff on every other commit.
    'COLUMNS': '80',
}


def run(command: str, cwd: str, expected_exit: int) -> tuple[str, str]:
    """Run `command`, returning its output and any error to report."""
    try:
        argv = shlex.split(command)
    except ValueError as exc:  # unbalanced quoting in the config
        return '', f'cannot parse --command: {exc}'
    if not argv:
        return '', 'empty --command'

    try:
        result = subprocess.run(  # noqa: S603
            argv,
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd,
            env={**os.environ, **_PLAIN_ENV},
        )
    except OSError as exc:
        return '', f'cannot run {argv[0]}: {exc}'

    if result.returncode != expected_exit:
        # Plenty of CLIs print usage and exit non-zero; that is a legitimate
        # thing to document, so point at the flag rather than just refusing.
        detail = (result.stderr or result.stdout).strip()
        return '', (
            f'`{command}` exited {result.returncode}, expected '
            f'{expected_exit}. Pass --exit={result.returncode} if that is '
            f'normal for it.\n{detail}'
        )

    # argparse and friends print usage to stdout; some hand-rolled CLIs use
    # stderr. Take whichever spoke, preferring stdout.
    return (result.stdout or result.stderr), ''


def _clean(output: str) -> str:
    """Strip trailing whitespace, so the block does not churn on rerun."""
    lines = [line.rstrip() for line in output.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return '\n'.join(lines)


def main(argv: list[str]) -> int:
    """Regenerate the command block, re-staging the file if it changed."""
    root = doc_block.repo_root()
    target = root / doc_block.flag(argv, 'file', DEFAULT_FILE)
    marker = doc_block.flag(argv, 'marker', DEFAULT_MARKER)
    command = doc_block.flag(argv, 'command', '')
    expected_exit = int(doc_block.flag(argv, 'exit', str(DEFAULT_EXIT)))

    if not command:
        sys.stderr.write(
            'embed-command: no --command given. This hook runs the command '
            "you name and nothing else:\n  args: ['--marker=help', "
            "'--command=mytool --help']\n",
        )
        return 1

    output, error = run(command, str(root), expected_exit)
    if error:
        sys.stderr.write(f'embed-command: {error}\n')
        return 1

    body = _clean(output)
    return doc_block.embed('embed-command', root, target, marker, body)
