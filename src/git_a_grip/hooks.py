"""The hook entry points, behind `python -m git_a_grip.hooks <name>`.

pre-commit does not need a console script: it shlex-splits a hook's `entry:`
and runs it with the hook env's `bin/` first on PATH, so `python` there is
the env's own interpreter and `-m` finds this module. Going through `-m`
rather than `[project.scripts]` means installing the package puts exactly
one thing on a person's PATH -- `gag` -- and the hooks stay unreachable by
name, which is what they were always meant to be.

Adding a hook is one entry in `HOOKS` plus its block in
`.pre-commit-hooks.yaml`; tests/test_packaging.py asserts the two agree.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from git_a_grip import commitizen_early, embed_command, embed_tree
from git_a_grip import mypy_hook, node_hooks, privacy_hook, pytest_hook
from git_a_grip import regen_file
from git_a_grip import ruff_hooks

Hook = Callable[[list[str]], int]

HOOKS: dict[str, Hook] = {
    'commitizen-early': lambda _argv: commitizen_early.main(),
    'embed-tree': embed_tree.main,
    'embed-command': embed_command.main,
    'regen-file': regen_file.main,
    'ruff-check': lambda argv: ruff_hooks.run('check', ['--fix', *argv]),
    'ruff-format': lambda argv: ruff_hooks.run('format', argv),
    'mypy': mypy_hook.main,
    'eslint': node_hooks.eslint,
    'tsc': node_hooks.tsc,
    'vitest': node_hooks.vitest,
    'pytest': pytest_hook.main,
    'block-private-terms': privacy_hook.main,
}

# Ids that shipped under an older name. A consuming repo pins a rev, so its
# config outlives the rename; dispatching the old name costs one dict and
# saves every consumer a broken commit on the day they bump.
ALIASES: dict[str, str] = {
    'readme-tree': 'embed-tree',
    'privacy-terms': 'block-private-terms',
}


def main(argv: list[str] | None = None) -> int:
    """Run the named hook against the rest of the argv."""
    args = sys.argv[1:] if argv is None else argv
    if not args:
        sys.stderr.write(
            'git-a-grip: usage: python -m git_a_grip.hooks <hook-id> [args]\n'
            'These are pre-commit entry points, not commands. '
            'For the commands, run `gag --help`.\n',
        )
        return 2

    name, *rest = args
    if name in ALIASES:
        current = ALIASES[name]
        sys.stderr.write(
            f'git-a-grip: `{name}` is now `{current}`. Still runs; rename it '
            'in .pre-commit-config.yaml when convenient.\n',
        )
        name = current
    hook = HOOKS.get(name)
    if hook is None:
        known = ', '.join(sorted(HOOKS))
        sys.stderr.write(
            f'git-a-grip: no such hook: {name}\nKnown hooks: {known}\n',
        )
        return 2

    return hook(rest)


def main_cli() -> None:
    """`python -m git_a_grip.hooks` entry point."""
    raise SystemExit(main())


if __name__ == '__main__':
    main_cli()
