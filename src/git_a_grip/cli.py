"""The `gag` command: one namespace for everything a person runs by hand.

The other entry points in `pyproject.toml` are hook entry points -- pre-commit
resolves them from `.pre-commit-hooks.yaml` and nobody types them. Keeping the
human commands behind a single dispatcher means `gag --help` is the whole
surface of the tool, and a new command costs one line in `COMMANDS`.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from git_a_grip import audit, hook_docs, release, sync, version

Command = Callable[[list[str]], int]

COMMANDS: dict[str, tuple[Command, str]] = {
    'hooks': (
        hook_docs.main,
        'Document the pre-commit hooks and how to turn each one on.',
    ),
    'audit': (
        audit.main,
        'Report which local repos use these hooks, and at what rev.',
    ),
    'sync': (
        sync.main,
        'Move every local repo onto one rev of these hooks.',
    ),
    'release': (
        release.main,
        'Bump the version, tag it, and push.',
    ),
}

USAGE = """\
usage: gag <command> [options]

commands:
{commands}

Run `gag <command> --help` for a command's own options.
Version: {version}
"""


def _usage() -> str:
    width = max(len(name) for name in COMMANDS)
    lines = '\n'.join(
        f'  {name.ljust(width)}  {help_text}'
        for name, (_, help_text) in COMMANDS.items()
    )
    return USAGE.format(commands=lines, version=version.installed_version())


def main(argv: list[str] | None = None) -> int:
    """Dispatch to a subcommand. 0 means it ran and was happy."""
    args = sys.argv[1:] if argv is None else argv

    if not args or args[0] in {'-h', '--help', 'help'}:
        sys.stdout.write(_usage())
        return 0
    if args[0] in {'-V', '--version', 'version'}:
        sys.stdout.write(f'{version.installed_version()}\n')
        return 0

    name, *rest = args
    command = COMMANDS.get(name)
    if command is None:
        sys.stderr.write(f'gag: unknown command: {name}\n\n')
        sys.stderr.write(_usage())
        return 2

    return command[0](rest)


def main_cli() -> None:
    """Console-script entry point."""
    raise SystemExit(main())


if __name__ == '__main__':
    main_cli()
