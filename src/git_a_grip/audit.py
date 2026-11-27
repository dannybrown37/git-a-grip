"""Inventory the pre-commit configs of every repo under a directory tree.

Answers the question a single `.pre-commit-config.yaml` cannot: across all
the repos on this machine, which of *this* repo's hooks are actually in use
and at what rev, what other third-party hooks have accumulated, and which
`repo: local` hooks exist only in one project and nowhere else.

    gag audit                 audit the sibling repos of this one
    gag audit ~/projects ~/wk audit those trees instead
    gag audit --json          the same data, machine-readable

Repos with no config at all are listed too -- an unhooked repo is a finding,
not an absence of one.

Each config is read from origin's default branch as of the last fetch, not
from the checkout. A clone untouched since its last release still has the
old rev on disk, and reporting that as `behind` sends you to bump a repo
whose default branch is already current. Where there is no origin, or
origin has no config, the working tree is the only evidence there is, and
`--json` names which one each repo came from.
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

from git_a_grip import doc_block, version

CONFIG_NAME = '.pre-commit-config.yaml'
SELF_MARKER = version.DIST_NAME
WORKING_TREE = 'working tree'
# origin/HEAD only exists in a repo that was cloned (or `remote set-head`);
# one created locally and pushed has the branch but not the pointer.
_ORIGIN_REFS = ('origin/HEAD', 'origin/main', 'origin/master')
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
gag audit -- audit the pre-commit hooks of every local repo.

  gag audit [PATH ...]  trees to scan (default: this repo's parent)
  gag audit --json      emit JSON instead of a report
  gag audit --help      show this
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
    config_from: str = ''

    @property
    def name(self) -> str:
        """The repo's directory name."""
        return self.path.name


def find_repos(roots: list[Path]) -> list[Path]:
    """Return every clone under `roots`, not recursing into one.

    A linked worktree (or submodule) has a `.git` *file* pointing back at a
    clone, so it is skipped: it is another checkout of a repo already
    counted, and often a live agent's workspace that `gag sync` must not
    edit underneath it.
    """
    found: list[Path] = []
    stack = [r.resolve() for r in roots]
    while stack:
        current = stack.pop()
        if not current.is_dir() or current.name in _PRUNED:
            continue
        dot_git = current / '.git'
        if dot_git.is_dir():
            found.append(current)
        if dot_git.exists():
            continue  # a checkout's subdirectories are part of that checkout
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


def _origin_config(path: Path) -> tuple[str, str] | None:
    """The config on origin's default branch, as of the last fetch.

    No fetch here: the audit stays offline, fast and read-only, and a repo
    fetched recently -- by `git pull`, an IDE, `gh` -- already has the ref.
    """
    # Only the first ref that resolves counts: falling through to a stale
    # origin/master because the real default branch dropped its config
    # would report a pin that is no longer anywhere that matters.
    for ref in _ORIGIN_REFS:
        if _git(path, 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}'):
            shown = _git(path, 'show', f'{ref}:{CONFIG_NAME}')
            return (ref, shown) if shown is not None else None
    return None


def _git(path: Path, *args: str) -> str | None:
    """Stdout of a git command, or None if it failed or git is missing."""
    try:
        done = subprocess.run(  # noqa: S603 -- fixed argv, no shell
            ['git', '-C', str(path), *args],  # noqa: S607
            capture_output=True,
            encoding='utf-8',
            errors='replace',
            check=False,
        )
    except OSError:
        return None
    return done.stdout if done.returncode == 0 else None


def audit_repo(path: Path, *, from_origin: bool = False) -> RepoAudit:
    """Read one repo's pre-commit config, tolerating a broken or absent one.

    `from_origin` reads what origin's default branch pins rather than the
    checkout, so a clone nobody has pulled since a release does not report
    as behind. Off by default: what the local git hooks enforce is the
    working tree, and that is what `gag remote`'s guard check needs.
    """
    origin = _origin_config(path) if from_origin else None
    if origin:
        config_from, text = origin
    else:
        config_from, config_path = WORKING_TREE, path / CONFIG_NAME
        if not config_path.is_file():
            return RepoAudit(path=path, has_config=False)
        try:
            text = config_path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as exc:
            return RepoAudit(path=path, error=str(exc).splitlines()[0])
    found = RepoAudit(path=path, config_from=config_from)
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        found.error = str(exc).splitlines()[0]
        return found
    if not isinstance(loaded, dict):
        found.error = 'config is not a mapping'
        return found
    found.uses = _hook_uses(loaded)
    return found


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


def rev_status(rev: str, current: str) -> str:
    """Describe one pinned rev relative to the installed version."""
    if not rev or current == version.UNKNOWN:
        return ''
    order = version.compare(rev, current)
    if order == 0:
        return 'current'
    return 'behind' if order < 0 else 'ahead'


def _self_section(audits: list[RepoAudit], current: str) -> list[str]:
    lines = []
    for hook_id, pairs in _group(audits, is_self).items():
        lines.append(f'  {hook_id}')
        for audit, use in sorted(pairs, key=lambda p: p[0].name):
            rev = use.rev or 'unpinned'
            status = rev_status(use.rev, current)
            note = f'  ({status})' if status and status != 'current' else ''
            lines.append(f'    {audit.name:<28} {rev:<12}{note}')
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
    current = version.installed_version()
    # The installed version leads the report: every rev below is only
    # meaningful next to the version they are being compared against.
    header = [
        f'{SELF_MARKER} {current} (installed)',
        f'{len(audits)} repos scanned, {hooked} with pre-commit hooks.',
        '',
    ]
    return '\n'.join(
        [
            *header,
            *_self_section(audits, current),
            *_third_party_section(audits),
            *_local_section(audits),
            *_gaps_section(audits),
        ],
    )


def as_json(audits: list[RepoAudit]) -> str:
    """Render the whole audit as JSON.

    The installed version is part of the payload for the same reason it
    heads the text report: a consumer comparing revs needs the thing they
    are compared to.
    """
    current = version.installed_version()
    repos = [
        {
            'path': str(a.path),
            'name': a.name,
            'has_config': a.has_config,
            'error': a.error,
            'config_from': a.config_from,
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
                    'status': (
                        rev_status(u.rev, current) if is_self(u) else ''
                    ),
                }
                for u in a.uses
            ],
        }
        for a in audits
    ]
    return json.dumps({'version': current, 'repos': repos}, indent=2)


def default_roots() -> list[Path]:
    """The directory holding this repo -- i.e. its sibling projects."""
    clone = doc_block.clone_root()
    return [clone.parent if clone else Path.cwd()]


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

    audits = [
        audit_repo(p, from_origin=True)
        for p in find_repos(paths or default_roots())
    ]
    sys.stdout.write((as_json if want_json else render)(audits) + '\n')
    return 0


def main_cli() -> None:
    """Console-script entry point."""
    raise SystemExit(main())


if __name__ == '__main__':
    main_cli()
