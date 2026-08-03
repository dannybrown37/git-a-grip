"""`gag hooks`: what the hooks are, and how to wire each one up.

The hooks are the half of this package nobody can discover by typing:
they have no console scripts, and `gag --help` lists commands. This command
is their index -- for each hook, what it does, the `.pre-commit-config.yaml`
block that turns it on, and the `python -m` line that runs it by hand when
you are debugging one.

Bare `gag hooks` is a one-line-per-hook list, because the full seven entries
are a screenful nobody reads to the end. The detail is a second command away,
for the one hook you actually came for.

The `description:` prose here is a second copy of the field of that name in
`.pre-commit-hooks.yaml`, because that file is not shipped in the wheel and
this command has to work from an install. tests/test_packaging.py asserts the
two copies still say the same thing, so the drift is caught rather than
shipped.

    gag hooks                 the list
    gag hooks ruff-check      one hook, in full
    gag hooks --all           every hook, in full
"""

from __future__ import annotations

import os
import sys
import textwrap
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from git_a_grip import version

if TYPE_CHECKING:
    from typing import TextIO


@dataclass(frozen=True)
class HookDoc:
    """One hook, as a person needs to see it."""

    name: str
    # One line for the list. Long enough to choose by, short enough to scan.
    summary: str
    # Verbatim from `.pre-commit-hooks.yaml`, and held there by a test.
    description: str
    # The lines that go under `hooks:` in a consuming .pre-commit-config.yaml.
    config: list[str] = field(default_factory=list)
    # Anything the description cannot say in a sentence.
    notes: str = ''


DOCS: dict[str, HookDoc] = {
    'commitizen-early': HookDoc(
        name='Commitizen check (early)',
        summary='Reject a bad commit message before the slow hooks run.',
        description=(
            'Reject a non-conventional commit message during the pre-commit '
            'stage, before the slow hooks run, by recovering it from '
            "git's argv."
        ),
        config=['- id: commitizen-early'],
        notes=(
            'Pair it with the upstream commitizen hook at the commit-msg '
            'stage: this one exits 0 and defers whenever argv holds no '
            'message (interactive editor, merge, rebase).'
        ),
    ),
    'ruff-check': HookDoc(
        name='Ruff check',
        summary='Lint with `ruff check --fix`, re-staging what it fixed.',
        description=(
            'Lint with `ruff check --fix`, re-staging the files it fixed so '
            'the fix is part of the commit rather than left dirty in the '
            'working tree.'
        ),
        config=['- id: ruff-check'],
        notes=(
            'Brings its own ruff through additional_dependencies. Pin yours '
            'with `additional_dependencies: [ruff==x.y.z]`.'
        ),
    ),
    'ruff-format': HookDoc(
        name='Ruff format',
        summary='Format with `ruff format`, re-staging what it rewrote.',
        description=(
            'Format with `ruff format`, re-staging the files it rewrote.'
        ),
        config=['- id: ruff-format'],
    ),
    'embed-tree': HookDoc(
        name='README file tree',
        summary='Regenerate the README file tree, and re-stage it.',
        description=(
            'Regenerate the file tree between the `<!-- tree:start -->` '
            'markers in the README from `git ls-files`, and re-stage it.'
        ),
        config=['- id: embed-tree', '  args: [--depth=3]  # optional'],
        notes=(
            'Does nothing until the README has both markers. `--depth=N` '
            'truncates below N levels (default: unlimited). Was `readme-tree` '
            'before 0.6; the old id still dispatches.'
        ),
    ),
    'embed-command': HookDoc(
        name='Embedded command output',
        summary="Keep a command's output (`--help`) true in the README.",
        description=(
            'Run the command named in `args` and keep its output -- '
            "`--help`, `make help` -- between that block's markers in the "
            'README, re-staging it.'
        ),
        config=[
            '- id: embed-command',
            "  args: ['--marker=help', '--command=uv run mytool --help']",
            '  files: ^(src/.*\\.py|README\\.md)$  # scope it yourself',
        ],
        notes=(
            'Runs only the command you write down -- nothing is discovered. '
            'One entry per block, each with its own `--marker`; the markers '
            'are `<!-- help:start -->` / `<!-- help:end -->` for '
            '`--marker=help`. A command that exits non-zero fails the commit '
            'rather than pasting its error into the README: pass '
            '`--exit=N` when that status is normal for it.'
        ),
    ),
    'eslint': HookDoc(
        name='ESLint',
        summary="Lint with the project's own eslint, re-staging fixes.",
        description=(
            "Lint with the project's own eslint (`--fix`, and "
            '`--max-warnings=0` unless you say otherwise), re-staging the '
            'files it fixed.'
        ),
        config=['- id: eslint', '  args: [--max-warnings=10]  # optional'],
        notes=(
            "Runs through the project's package manager, detected from the "
            'lockfile (pnpm, bun, yarn, else npx) and overridable with '
            '`--runner=...`.'
        ),
    ),
    'tsc': HookDoc(
        name='TypeScript',
        summary="Type-check the project with the project's own tsc.",
        description=(
            "Type-check the project with the project's own tsc. Never passes "
            'filenames -- tsc ignores tsconfig.json when it is given any.'
        ),
        config=['- id: tsc', '  args: [-p, tsconfig.build.json]  # optional'],
        notes='Type-checks `-p .` unless you name another project.',
    ),
    'pytest': HookDoc(
        name='Tests',
        summary="Run the repo's tests through its own environment.",
        description=(
            "Run the consuming repo's test suite from the repo root, through "
            "a runner that resolves the project's own environment (`uv run "
            'pytest` by default, override with `--runner=...`).'
        ),
        config=['- id: pytest', '  args: [tests/, -q]  # optional'],
        notes=(
            'The one hook that needs something outside the env pre-commit '
            'builds -- your tests import your project, so they need your '
            "project's environment."
        ),
    ),
}

_ENTRY = 'python -m git_a_grip.hooks'

_USAGE = """\
usage: gag hooks [hook-id | --all]

Document this repo's pre-commit hooks: what each one does, the
.pre-commit-config.yaml block that turns it on, and the command that runs it
by hand. With no argument, one line per hook.

hooks: {hooks}
"""


class Style:
    """ANSI codes, or empty strings where color is unwanted.

    Color is decoration: the same text has to read on a dumb terminal, in a
    pipe, and under NO_COLOR. Every escape goes through here so that turning
    it off is one branch rather than seven.
    """

    _CODES: ClassVar[dict[str, str]] = {
        'bold': '\x1b[1m',
        'dim': '\x1b[2m',
        'cyan': '\x1b[36m',
        'reset': '\x1b[0m',
    }

    def __init__(self, *, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, text: str, code: str) -> str:
        if not self.enabled:
            return text
        return f'{self._CODES[code]}{text}{self._CODES["reset"]}'


def style_for(stream: TextIO) -> Style:
    """Decide whether output to this stream should carry color."""
    return Style(
        enabled=bool(
            not os.environ.get('NO_COLOR')
            and os.environ.get('TERM') != 'dumb'
            and getattr(stream, 'isatty', bool)(),
        ),
    )


def _wrap(text: str, indent: str, width: int = 76) -> list[str]:
    return textwrap.wrap(
        ' '.join(text.split()),
        width=width,
        initial_indent=indent,
        subsequent_indent=indent,
    )


def _header(paint: Style) -> str:
    installed = version.installed_version()
    return '\n'.join(
        [
            paint(f'git-a-grip {installed} -- pre-commit hooks', 'bold'),
            '',
            paint('Turn one on in .pre-commit-config.yaml:', 'dim'),
            '',
            paint(
                '\n'.join(
                    [
                        'repos:',
                        f'  - repo: {version.REPO_URL}',
                        f'    rev: {version.as_rev(installed)}',
                        '    hooks:',
                        '      - id: <one of the below>',
                        '      - id: <...any number of others>',
                    ],
                ),
                'cyan',
            ),
            '',
        ],
    )


def _listing(paint: Style) -> str:
    width = max(len(hook_id) for hook_id in DOCS)
    lines = [
        # Pad outside the escape: bolding trailing spaces underlines them
        # on some terminals, and the column has to line up either way.
        f'  {paint(hook_id, "bold")}{" " * (width - len(hook_id))}  '
        f'{doc.summary}'
        for hook_id, doc in DOCS.items()
    ]
    lines += [
        '',
        paint(
            'gag hooks <id> for one in full, gag hooks --all for all of them.',
            'dim',
        ),
    ]
    return '\n'.join(lines)


def _entry(hook_id: str, doc: HookDoc, paint: Style) -> str:
    lines = [
        f'{paint(hook_id, "bold")} -- {doc.name}',
        *_wrap(doc.description, '  '),
    ]
    if doc.notes:
        lines += ['', *_wrap(doc.notes, '  ')]
    lines += ['', f'  {paint("config:", "dim")}']
    lines += [paint(f'    {line}', 'cyan') for line in doc.config]
    lines += [
        '',
        f'  {paint("by hand:", "dim")} {paint(f"{_ENTRY} {hook_id}", "cyan")}',
        '',
    ]
    return '\n'.join(lines)


def main(argv: list[str]) -> int:
    """Document the hooks. 0 means it printed something."""
    paint = style_for(sys.stdout)

    if argv and argv[0] in {'-h', '--help'}:
        sys.stdout.write(_USAGE.format(hooks=', '.join(DOCS)))
        return 0

    if argv and argv[0] == '--all':
        sys.stdout.write(_header(paint))
        for hook_id, doc in DOCS.items():
            sys.stdout.write(f'\n{_entry(hook_id, doc, paint)}')
        return 0

    if not argv:
        sys.stdout.write(f'{_header(paint)}\n{_listing(paint)}\n')
        return 0

    wanted = argv[0]
    doc = DOCS.get(wanted)
    if doc is None:
        known = ', '.join(DOCS)
        sys.stderr.write(
            f'gag hooks: no such hook: {wanted}\nKnown hooks: {known}\n',
        )
        return 2

    sys.stdout.write(_entry(wanted, doc, paint))
    return 0
