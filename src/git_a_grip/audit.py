"""Inventory the pre-commit configs of every repo under a directory tree.

Answers the question a single `.pre-commit-config.yaml` cannot: across all
the repos on this machine, which of *this* repo's hooks are actually in use
and at what rev, what other third-party hooks have accumulated, and which
`repo: local` hooks exist only in one project and nowhere else.

    pre-commit-audit                 audit the sibling repos of this one
    pre-commit-audit ~/projects ~/wk audit those trees instead
    pre-commit-audit --json          the same data, machine-readable

Repos with no config at all are listed too -- an unhooked repo is a finding,
not an absence of one.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_NAME = '.pre-commit-config.yaml'
SELF_MARKER = 'git-a-grip'
# Directories that never contain a repo we care about but do contain
# thousands of files, including vendored copies of other repos' configs.
_PRUNED = {
    '.git',
    '.venv',
    'node_modules',
    '__pycache__',
    '.tox',
    '.mypy_cache',
}

USAGE = """\
pre-commit-audit -- audit the pre-commit hooks of every local repo.

  pre-commit-audit [PATH ...]  trees to scan (default: this repo's parent)
  pre-commit-audit --json      emit JSON instead of a report
  pre-commit-audit --help      show this
"""


@dataclass
class HookUse:
    """One hook id, as used by one repo, from one source repo at one rev."""

    repo: str
    rev: str
    hook_id: str
    entry: str = ''


@dataclass
class RepoAudit:
    """Everything one local repo declares."""

    path: Path
    has_config: bool = True
    error: str = ''
    uses: list[HookUse] = field(default_factory=list)

    @property
    def name(self) -> str:
        """The repo's directory name."""
        return self.path.name


def find_repos(roots: list[Path]) -> list[Path]:
    """Return every git working tree under `roots`, not recursing into one."""
    found: list[Path] = []
    stack = [r.resolve() for r in roots]
    while stack:
        current = stack.pop()
        if not current.is_dir() or current.name in _PRUNED:
            continue
        if (current / '.git').exists():
            found.append(current)
            continue  # a repo's subdirectories are part of that repo
        stack.extend(child for child in current.iterdir() if child.is_dir())
    return sorted(found)


def _hook_uses(config: dict[str, Any]) -> list[HookUse]:
    uses = []
    for entry in config.get('repos') or []:
        if not isinstance(entry, dict):
            continue
        source = str(entry.get('repo', '?'))
        rev = str(entry.get('rev', '')) if entry.get('rev') else ''
        for hook in entry.get('hooks') or []:
            if not isinstance(hook, dict):
                continue
            uses.append(
                HookUse(
                    repo=source,
                    rev=rev,
                    hook_id=str(hook.get('id', '?')),
                    entry=str(hook.get('entry', '')),
                ),
            )
    return uses


def audit_repo(path: Path) -> RepoAudit:
    """Read one repo's pre-commit config, tolerating a broken or absent one."""
    config_path = path / CONFIG_NAME
    if not config_path.is_file():
        return RepoAudit(path=path, has_config=False)
    try:
        loaded = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
        return RepoAudit(path=path, error=str(exc).splitlines()[0])
    if not isinstance(loaded, dict):
        return RepoAudit(path=path, error='config is not a mapping')
    return RepoAudit(path=path, uses=_hook_uses(loaded))


def is_self(use: HookUse) -> bool:
    """Whether this use comes from this project's hooks."""
    return SELF_MARKER in use.repo


def is_local(use: HookUse) -> bool:
    """Whether this use is a `repo: local` (or `meta`) hook."""
    return use.repo in {'local', 'meta'}


def _group(
    audits: list[RepoAudit],
    predicate: Any,  # noqa: ANN401 -- Callable[[HookUse], bool]
) -> dict[str, list[tuple[RepoAudit, HookUse]]]:
    grouped: dict[str, list[tuple[RepoAudit, HookUse]]] = defaultdict(list)
    for audit in audits:
        for use in audit.uses:
            if predicate(use):
                grouped[use.hook_id].append((audit, use))
    return dict(sorted(grouped.items()))


def _section(title: str, lines: list[str]) -> list[str]:
    return [title, '=' * len(title), *(lines or ['  (none)']), '']


def _self_section(audits: list[RepoAudit]) -> list[str]:
    lines = []
    for hook_id, pairs in _group(audits, is_self).items():
        lines.append(f'  {hook_id}')
        for audit, use in sorted(pairs, key=lambda p: p[0].name):
            rev = use.rev or 'unpinned'
            lines.append(f'    {audit.name:<28} {rev}')
    return _section(f'{SELF_MARKER} hooks in use', lines)


def _third_party_section(audits: list[RepoAudit]) -> list[str]:
    by_source: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set),
    )
    for audit in audits:
        for use in audit.uses:
            if is_self(use) or is_local(use):
                continue
            label = f'{use.hook_id} @ {use.rev or "unpinned"}'
            by_source[use.repo][label].add(audit.name)
    lines = []
    for source, hooks in sorted(by_source.items()):
        lines.append(f'  {source}')
        for label, users in sorted(hooks.items()):
            lines.append(f'    {label:<40} {", ".join(sorted(users))}')
    return _section('Third-party hooks', lines)


def _local_section(audits: list[RepoAudit]) -> list[str]:
    lines = []
    for audit in audits:
        local = [use for use in audit.uses if is_local(use)]
        if not local:
            continue
        lines.append(f'  {audit.name}')
        for use in local:
            entry = use.entry or '(no entry)'
            lines.append(f'    {use.hook_id:<24} {entry}')
    return _section('Local hooks (defined in one repo only)', lines)


def _gaps_section(audits: list[RepoAudit]) -> list[str]:
    lines = [
        f'  {audit.name:<28} {audit.error or "no " + CONFIG_NAME}'
        for audit in audits
        if not audit.has_config or audit.error
    ]
    return _section('Repos with no usable config', lines)


def render(audits: list[RepoAudit]) -> str:
    """Render the whole audit as a plain-text report."""
    hooked = sum(1 for a in audits if a.uses)
    header = [
        f'{len(audits)} repos scanned, {hooked} with pre-commit hooks.',
        '',
    ]
    return '\n'.join(
        [
            *header,
            *_self_section(audits),
            *_third_party_section(audits),
            *_local_section(audits),
            *_gaps_section(audits),
        ],
    )


def as_json(audits: list[RepoAudit]) -> str:
    """Render the whole audit as JSON."""
    return json.dumps(
        [
            {
                'path': str(a.path),
                'name': a.name,
                'has_config': a.has_config,
                'error': a.error,
                'hooks': [
                    {
                        'repo': u.repo,
                        'rev': u.rev,
                        'id': u.hook_id,
                        'entry': u.entry,
                        'source': (
                            'self'
                            if is_self(u)
                            else 'local'
                            if is_local(u)
                            else 'third-party'
                        ),
                    }
                    for u in a.uses
                ],
            }
            for a in audits
        ],
        indent=2,
    )


def default_roots() -> list[Path]:
    """The directory holding this repo -- i.e. its sibling projects."""
    top = subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return [Path(top).parent if top else Path.cwd()]


def main(argv: list[str] | None = None) -> int:
    """Scan, report, and return 0 unless the arguments make no sense."""
    args = sys.argv[1:] if argv is None else argv
    if '--help' in args or '-h' in args:
        sys.stdout.write(USAGE)
        return 0
    want_json = '--json' in args
    paths = [Path(a) for a in args if not a.startswith('-')]
    missing = [p for p in paths if not p.is_dir()]
    if missing:
        sys.stderr.write(
            f'audit: not a directory: {", ".join(str(p) for p in missing)}\n',
        )
        return 2

    audits = [audit_repo(p) for p in find_repos(paths or default_roots())]
    sys.stdout.write((as_json if want_json else render)(audits) + '\n')
    return 0


def main_cli() -> None:
    """Console-script entry point."""
    raise SystemExit(main())


if __name__ == '__main__':
    main_cli()
