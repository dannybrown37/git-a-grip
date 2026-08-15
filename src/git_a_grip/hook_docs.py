"""`gag hooks`: what the hooks are, and how to wire each one up.

The hooks are the half of this package nobody can discover by typing:
they have no console scripts, and `gag --help` lists commands. This command
is their index -- for each hook, what it does, the `.pre-commit-config.yaml`
block that turns it on, and the `python -m` line that runs it by hand when
you are debugging one.

Bare `gag hooks` is a one-line-per-hook list, because the full set of entries
is a screenful nobody reads to the end. The detail is a second command away,
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
    'mypy': HookDoc(
        name='Mypy',
        summary='Type-check the project in its own environment.',
        description=(
            'Type-check the project with mypy, through a runner that '
            "resolves the project's own environment and installs the "
            'checker into it (`uv run --with mypy mypy` by default, so '
            'mypy need not be declared anywhere). Passes no targets of its '
            'own, so the hook checks what `mypy` checks by hand.'
        ),
        config=['- id: mypy'],
        notes=(
            'Runs in your project, not in the env pre-commit built: a type '
            'checker that cannot import your dependencies reports on the '
            'imports instead of on your code. The default runner adds mypy '
            'with `uv run --with`, so there is no dependency group to '
            'declare and none to keep in step; a project that pins its own '
            'mypy still wins. It names no files, so mypy takes them from '
            '`files`/`packages`/`modules` in your mypy config -- which is '
            'what makes the hook and the terminal agree, and is the one '
            'line of config this hook does want from you. Naming them in '
            '`args` instead works and lets the two diverge. Point '
            '`--runner=` at `uv run --with pyright pyright` or `uv run ty '
            'check` to swap the engine.'
        ),
    ),
    'block-private-terms': HookDoc(
        name='Block private terms',
        summary='Block a commit adding one of your own private terms.',
        description=(
            'Block a commit that adds a line matching one of your own '
            'private terms -- an employer, a client, a hostname -- read '
            'from a file only you have, never from the repo.'
        ),
        config=[
            '- id: block-private-terms',
            '  args: [--word]  # optional',
        ],
        notes=(
            'A secret scanner finds credentials because a credential looks '
            'like one. These are ordinary words, sensitive only because of '
            'who typed them, so the terms live outside the tree: the first '
            'of `--terms-file=`, `$GAG_PRIVACY_TERMS_FILE`, '
            '`$XDG_CONFIG_HOME/git-a-grip/privacy-terms`, or '
            '`<repo>/.git/privacy-terms`. Manage them with `gag privacy`. '
            'With no terms configured it warns and passes, so the hook '
            'survives a machine that never set it up; a terms file the rest '
            'of the machine can read fails instead, because believing you '
            'are covered is worse than knowing you are not. Only added '
            'lines are read, and the output names the file and line but '
            'never the match -- it ends up in CI logs. `--word` requires a '
            'word boundary, for a short term that would otherwise match '
            'inside other words.'
        ),
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
    'regen-file': HookDoc(
        name='Regenerated file',
        summary='Run a generator script, and re-stage what it rewrote.',
        description=(
            'Run the generator named in `args` and re-stage the files it '
            'rewrote, for a script that owns a whole file rather than a '
            'marked block.'
        ),
        config=[
            '- id: regen-file',
            "  args: ['--command=uv run python scripts/update_readme.py',",
            "         '--file=README.md']",
            '  files: ^(src/.*\\.py|README\\.md)$  # scope it yourself',
        ],
        notes=(
            'The replacement for '
            "`bash -c 'run-the-script && git add the-file'`. Runs only the "
            'command you write down, without a shell -- nothing is '
            'discovered, and `&&` is an argument rather than a second '
            'command. `--file` repeats for a script that writes more than '
            'one. A file is staged only when its contents actually moved, '
            'and a `--file` the command did not write fails the commit '
            'rather than passing an empty run off as a clean one. Use '
            '`embed-command` instead when the script owns only the region '
            'between two markers.'
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
            'nearest lockfile (pnpm, bun, yarn, else npx) and overridable '
            'with `--runner=...`. `--dir=web` runs it from a subdirectory, '
            'for a monorepo whose eslint config and node_modules live there; '
            'files outside that subdirectory are skipped.'
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
        notes=(
            'Type-checks `-p .` unless you name another project. `--dir=web` '
            'runs it from a subdirectory, where `.` is that subdirectory and '
            'so is the tsconfig.json it picks up.'
        ),
    ),
    'vitest': HookDoc(
        name='Vitest',
        summary="Run the project's vitest suite once, never in watch mode.",
        description=(
            "Run the project's vitest suite once with `vitest run` -- never "
            'the watch mode a bare `vitest` starts, which would hang the '
            'commit.'
        ),
        config=['- id: vitest', '  args: [--dir=web]  # optional'],
        notes=(
            'Runs the whole suite, never the changed files. `CI=true` is set, '
            'so a missing snapshot fails rather than being written and '
            'committed as though it had passed. `--dir=web` runs it from a '
            'subdirectory; `--runner=...` replaces the command outright, so '
            'say `--runner=npm test -- --run` in full.'
        ),
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
            # No version in the title. This block is embedded in the README,
            # where the only version anyone should read is the `rev` they
            # paste -- and that one commitizen rewrites in the bump commit
            # (`version_files`). A second copy up here has no such owner, so
            # it drifts to whatever the last contributor had installed.
            paint('git-a-grip -- pre-commit hooks', 'bold'),
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
        for hook_id, doc in sorted(DOCS.items())
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
        sys.stdout.write(_USAGE.format(hooks=', '.join(sorted(DOCS))))
        return 0

    if argv and argv[0] == '--all':
        sys.stdout.write(_header(paint))
        for hook_id, doc in sorted(DOCS.items()):
            sys.stdout.write(f'\n{_entry(hook_id, doc, paint)}')
        return 0

    if not argv:
        sys.stdout.write(f'{_header(paint)}\n{_listing(paint)}\n')
        return 0

    wanted = argv[0]
    # Not `doc`: the --all branch above binds that name to a HookDoc, and a
    # second binding of `HookDoc | None` is the kind of shadowing a type
    # checker is right to complain about.
    found = DOCS.get(wanted)
    if found is None:
        known = ', '.join(sorted(DOCS))
        sys.stderr.write(
            f'gag hooks: no such hook: {wanted}\nKnown hooks: {known}\n',
        )
        return 2

    sys.stdout.write(_entry(wanted, found, paint))
    return 0
