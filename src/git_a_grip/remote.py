"""Show the GitHub side of every local repo, one line each.

`gag audit` answers what each repo declares on disk. This answers what the
disk cannot: is the default branch protected, is its CI green, when did
anything last run or land, and what is waiting in PRs and issues. Pre-commit
only guards commits made on a machine that has it installed; branch
protection is what stops a `--no-verify` push reaching `main`, so the two
belong in the same sweep.

    gag remote                 the sibling repos of this one
    gag remote ~/projects      those trees instead
    gag remote --json          the same data, machine-readable

Everything goes through `gh api`, so there is no token handling here and no
new dependency -- whatever `gh auth login` can see is what gets reported.
The repo list comes from the local tree, not from the GitHub account: the
question is about the projects you actually work on, and a clone with no
GitHub remote is itself worth a line.

Some local repos will never need attention -- a vendored fork, an archive
kept for reference. Naming them in `$XDG_CONFIG_HOME/git-a-grip/remote-skip`
drops them before any `gh` call, so they cost nothing rather than five API
round-trips each. The file is per person, not per repo, for the same reason
the repo list is local: which projects matter is the reader's call.

Where GitHub declines to say what guards a branch -- a private repo on a
free plan -- the next best answer is on disk: a pre-commit config that
refuses pushes to it (`protect-branch`) or commits (upstream
`no-commit-to-branch`). That shows as `pre-commit`, or `uninstalled` when
the config asks for it but the git hook for its stage was never installed.
Amber, never green: `--no-verify` walks past it, and a push from any other
machine never meets it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Self, TextIO

from git_a_grip import audit

USAGE = """\
gag remote -- GitHub status of every local repo, at a glance.

  gag remote [PATH ...]  trees to scan (default: this repo's parent)
  gag remote --all-repos include repos with no commit in 90 days
  gag remote --json      emit JSON instead of a table
  gag remote --help      show this

Repos named in ~/.config/git-a-grip/remote-skip (one directory name per
line, # for comments) are never checked.

Needs `gh` on PATH and logged in (`gh auth login`).
"""

Gh = Callable[[str], tuple[int, Any]]

# The URL is interpolated into a `gh api` path, so anything outside GitHub's
# own name alphabet is treated as not-GitHub rather than passed along.
_SLUG = re.compile(
    r'github\.com[:/]'
    r'(?P<owner>[A-Za-z0-9-]+)/'
    r'(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$',
)
_HTTP_STATUS = re.compile(r'\(HTTP (\d{3})\)')
_RUNS_PER_PAGE = 30
_WORKERS = 8
RECENT_DAYS = 90
# Hook id -> the git hook it runs from; installed at the other stage, it
# never runs at all.
_BRANCH_GUARDS = {
    'protect-branch': 'pre-push',
    'no-commit-to-branch': 'pre-commit',
}
_SECURITY = {
    'secret_scanning': 'secret-scanning',
    'secret_scanning_push_protection': 'push-protection',
    'dependabot_security_updates': 'dependabot',
}


@dataclass
class RemoteStatus:
    """What GitHub says about one repo's default branch and backlog."""

    branch: str = ''
    visibility: str = ''
    archived: bool = False
    protection: str = ''
    ci: str = ''
    last_run: str = ''
    pushed_at: str = ''
    open_prs: int | None = None
    open_issues: int | None = None
    security: list[str] = field(default_factory=list)
    error: str = ''


@dataclass
class RepoRemote:
    """One local repo and, if it lives on GitHub, its status there."""

    name: str
    slug: str
    note: str = ''
    status: RemoteStatus | None = None
    local_guard: str = ''


def parse_github_slug(url: str) -> tuple[str, str] | None:
    """Return (owner, repo) for a GitHub remote URL, else None."""
    match = _SLUG.search(url.strip())
    if not match or match['repo'] in {'.', '..'}:
        return None
    return match['owner'], match['repo']


def skip_path() -> Path:
    """The per-person list of repo names `gag remote` never checks."""
    config = os.environ.get('XDG_CONFIG_HOME')
    root = Path(config) if config else Path.home() / '.config'
    return root / 'git-a-grip' / 'remote-skip'


def read_skips(path: Path) -> set[str]:
    """Return the repo names in a skip file; a missing file skips none."""
    try:
        text = path.read_text()
    except FileNotFoundError:
        return set()
    lines = (line.strip() for line in text.splitlines())
    return {line for line in lines if line and not line.startswith('#')}


def gh_api(path: str) -> tuple[int, Any]:
    """Call `gh api` and return (HTTP status, parsed body)."""
    proc = subprocess.run(  # noqa: S603 -- path is built from a validated slug
        ['gh', 'api', path],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        body = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        body = {}
    if proc.returncode == 0:
        return 200, body
    found = _HTTP_STATUS.search(proc.stderr)
    return (int(found[1]) if found else 0), body


def age(stamp: str, now: datetime) -> str:
    """Render an ISO-8601 timestamp as a coarse 'N units ago'."""
    if not stamp:
        return '-'
    then = datetime.fromisoformat(stamp)
    seconds = int((now - then).total_seconds())
    if seconds < 60:  # noqa: PLR2004
        return 'just now'
    for unit, size in (('d', 86400), ('h', 3600), ('m', 60)):
        if seconds >= size:
            return f'{seconds // size}{unit} ago'
    return 'just now'


def ci_status(runs: list[dict[str, Any]]) -> tuple[str, str]:
    """Summarise a branch's runs as (worst latest outcome, newest time).

    Only each workflow's newest run counts -- an old failure since fixed is
    not a red build -- but every workflow counts, so a green release job
    cannot hide a red test job that happened to run earlier.
    """
    latest: dict[Any, dict[str, Any]] = {}
    for run in sorted(runs, key=lambda r: r['updated_at'], reverse=True):
        latest.setdefault(run['workflow_id'], run)
    if not latest:
        return 'none', ''
    outcomes = {
        run['conclusion'] if run['status'] == 'completed' else 'running'
        for run in latest.values()
    }
    newest = max(run['updated_at'] for run in latest.values())
    for worst in ('failure', 'timed_out', 'running', 'cancelled'):
        if worst in outcomes:
            return worst, newest
    if outcomes <= {'success', 'skipped', 'neutral'}:
        return 'success', newest
    return ', '.join(sorted(o for o in outcomes if o)), newest


def _protection(owner: str, repo: str, branch: str, gh: Gh) -> str:
    classic, _ = gh(f'repos/{owner}/{repo}/branches/{branch}/protection')
    rules_code, rules = gh(f'repos/{owner}/{repo}/rules/branches/{branch}')
    # 403 is GitHub declining to answer (private repo, free plan), which is
    # not the same as knowing the branch is open.
    if classic == 403 and rules_code == 403:  # noqa: PLR2004
        return 'unknown'
    sources = []
    if classic == 200:  # noqa: PLR2004
        sources.append('classic')
    if rules_code == 200 and rules:  # noqa: PLR2004
        sources.append('ruleset')
    return '+'.join(sources) or 'none'


def fetch_status(owner: str, repo: str, gh: Gh = gh_api) -> RemoteStatus:
    """Collect one repo's status; a failure lands in `error`, not a raise."""
    code, info = gh(f'repos/{owner}/{repo}')
    if code != 200:  # noqa: PLR2004
        message = info.get('message') if isinstance(info, dict) else ''
        return RemoteStatus(error=message or f'HTTP {code}')
    branch = info.get('default_branch', '')
    _, runs = gh(
        f'repos/{owner}/{repo}/actions/runs'
        f'?branch={branch}&per_page={_RUNS_PER_PAGE}',
    )
    ci, last_run = ci_status(
        runs.get('workflow_runs', []) if isinstance(runs, dict) else [],
    )
    prs_code, prs = gh(f'repos/{owner}/{repo}/pulls?state=open&per_page=100')
    open_prs = len(prs) if prs_code == 200 else None  # noqa: PLR2004
    analysis = info.get('security_and_analysis') or {}
    return RemoteStatus(
        branch=branch,
        visibility=info.get('visibility', ''),
        archived=bool(info.get('archived')),
        protection=_protection(owner, repo, branch, gh),
        ci=ci,
        last_run=last_run,
        pushed_at=info.get('pushed_at', ''),
        open_prs=open_prs,
        open_issues=(
            info.get('open_issues_count', 0) - open_prs
            if open_prs is not None
            else None
        ),
        security=[
            label
            for key, label in _SECURITY.items()
            if (analysis.get(key) or {}).get('status') == 'enabled'
        ],
    )


def _origin_url(path: Path) -> str:
    return subprocess.run(  # noqa: S603 -- fixed argv, no shell
        ['git', '-C', str(path), 'remote', 'get-url', 'origin'],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


def local_guard(path: Path) -> str:
    """Whether a pre-commit hook guards the default branch, and is live."""
    stages = {
        _BRANCH_GUARDS[use.hook_id]
        for use in audit.audit_repo(path).uses
        if use.hook_id in _BRANCH_GUARDS
    }
    if not stages:
        return ''
    live = any(_git_hook_installed(path, stage) for stage in stages)
    return 'pre-commit' if live else 'uninstalled'


def _git_hook_installed(path: Path, stage: str) -> bool:
    # --git-path, because hooks live elsewhere in a worktree or under
    # core.hooksPath, and a config that is never installed guards nothing.
    hook = subprocess.run(  # noqa: S603 -- fixed argv, no shell
        ['git', '-C', str(path), 'rev-parse', '--git-path', f'hooks/{stage}'],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return bool(hook) and (path / hook).is_file()


def inspect(path: Path, gh: Gh = gh_api) -> RepoRemote:
    """Resolve one local repo to its GitHub status."""
    url = _origin_url(path)
    slug = parse_github_slug(url)
    if slug is None:
        note = 'no origin remote' if not url else 'no GitHub remote'
        return RepoRemote(name=path.name, slug='', note=note)
    owner, repo = slug
    return RepoRemote(
        name=path.name,
        slug=f'{owner}/{repo}',
        status=fetch_status(owner, repo, gh),
        local_guard=local_guard(path),
    )


RED = '\x1b[31m'
GREEN = '\x1b[32m'
YELLOW = '\x1b[33m'
_RESET = '\x1b[0m'
_ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
# Unprotected is the finding, so it is spelled out in red; everything that
# is merely absent or unanswerable renders blank so the eye skips it.
_COLOURS = {
    'none': RED,
    'classic': GREEN,
    'ruleset': GREEN,
    'classic+ruleset': GREEN,
    'pre-commit': YELLOW,
    'uninstalled': YELLOW,
    'success': GREEN,
    'failure': RED,
    'timed_out': RED,
    'running': YELLOW,
    'cancelled': YELLOW,
}
_BLANK_PROTECTION = {'unknown'}
_BLANK_CI = {'none'}


def strip_ansi(text: str) -> str:
    """Remove colour codes, leaving what a plain terminal would show."""
    return _ANSI.sub('', text)


def use_colour(stream: TextIO) -> bool:
    """Colour only for a person at a terminal who has not opted out."""
    return stream.isatty() and 'NO_COLOR' not in os.environ


def _cell(text: str, width: int, *, colour: bool) -> str:
    # Pad first, then colour: escape codes have no width on screen but do
    # have length, and padding them would skew every column after.
    padded = f'{text:<{width}}'
    tint = _COLOURS.get(text) if colour else None
    return f'{tint}{padded}{_RESET}' if tint else padded


def _count(value: int | None) -> str:
    return str(value) if value else ''


def _age(stamp: str, now: datetime) -> str:
    return age(stamp, now) if stamp else ''


def _row(item: RepoRemote, now: datetime, *, colour: bool) -> str:
    status = item.status
    if status is None:
        return f'  {item.name:<24} {item.note}'
    if status.error:
        return f'  {item.name:<24} {item.slug}: {status.error}'
    protection = (
        item.local_guard
        if status.protection in _BLANK_PROTECTION
        else status.protection
    )
    ci = '' if status.ci in _BLANK_CI else status.ci
    flags = ' archived' if status.archived else ''
    return (
        f'  {item.name:<24} {status.branch:<8} '
        f'{_cell(protection, 16, colour=colour)}'
        f'{_cell(ci, 10, colour=colour)} {_age(status.last_run, now):<10}'
        f'{_age(status.pushed_at, now):<10}'
        f'{_count(status.open_prs):>3} {_count(status.open_issues):>4}  '
        f'{",".join(status.security)}{flags}'
    )


def render(
    rows: list[RepoRemote],
    now: datetime,
    *,
    colour: bool = False,
    hidden: int = 0,
    skipped: int = 0,
) -> str:
    """Render the sweep as a table with a one-line tally on top."""
    statuses = [r.status for r in rows if r.status and not r.status.error]
    unprotected = sum(1 for s in statuses if s.protection == 'none')
    failing = sum(1 for s in statuses if s.ci in {'failure', 'timed_out'})
    header = (
        f'  {"repo":<24} {"branch":<8} {"protection":<16}{"ci":<10} '
        f'{"last run":<10}{"pushed":<10}{"prs":>3} {"iss":>4}  security'
    )
    footer = (
        [
            '',
            (
                f'{hidden} repos untouched in {RECENT_DAYS} days hidden '
                '(--all-repos to show).'
            ),
        ]
        if hidden
        else []
    ) + (['', f'{skipped} repos skipped by {skip_path()}.'] if skipped else [])
    return '\n'.join(
        [
            (
                f'{len(rows)} repos, {len(statuses)} on GitHub: '
                f'{unprotected} unprotected, {failing} failing.'
            ),
            '',
            header,
            *(_row(r, now, colour=colour) for r in rows),
            *footer,
        ],
    )


def last_touched(path: Path) -> datetime | None:
    """When anything was last committed, on any branch; None if never."""
    stamp = subprocess.run(  # noqa: S603 -- fixed argv, no shell
        ['git', '-C', str(path), 'log', '-1', '--all', '--format=%cI'],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return datetime.fromisoformat(stamp) if stamp else None


def select_recent(
    repos: list[Path],
    now: datetime,
    touched: Callable[[Path], datetime | None] = last_touched,
) -> list[Path]:
    """Keep the repos committed to within `RECENT_DAYS`."""
    cutoff = now - timedelta(days=RECENT_DAYS)
    return [
        repo
        for repo in repos
        if (when := touched(repo)) is not None and when >= cutoff
    ]


class Progress:
    """A single self-erasing 'checking n/total' line on a terminal.

    The sweep takes seconds of silence otherwise, which reads as a hang.
    Off a terminal it writes nothing, so piped `--json` stays clean.
    """

    def __init__(self, total: int, stream: TextIO) -> None:
        """Track `total` items, drawing on `stream` if it is a terminal."""
        self.total = total
        self.done = 0
        self.stream = stream
        self.live = stream.isatty()
        self._lock = threading.Lock()

    def __enter__(self) -> Self:
        """Draw the initial 0/total line."""
        self._draw()
        return self

    def __exit__(self, *_: object) -> None:
        """Erase the line so the report starts on a clean one."""
        if self.live:
            self.stream.write('\r\x1b[K')
            self.stream.flush()

    def tick(self) -> None:
        """Count one item done."""
        with self._lock:
            self.done += 1
            self._draw()

    def _draw(self) -> None:
        if self.live:
            self.stream.write(
                f'\rchecking {self.done}/{self.total} repos on GitHub...',
            )
            self.stream.flush()


def as_json(rows: list[RepoRemote]) -> str:
    """Render the sweep as JSON, with raw timestamps rather than ages."""
    return json.dumps({'repos': [asdict(r) for r in rows]}, indent=2)


def main(argv: list[str] | None = None) -> int:
    """Sweep and report; 0 unless the arguments or `gh` are unusable."""
    args = sys.argv[1:] if argv is None else argv
    if '--help' in args or '-h' in args:
        sys.stdout.write(USAGE)
        return 0
    want_json = '--json' in args
    paths = [Path(a) for a in args if not a.startswith('-')]
    missing = [p for p in paths if not p.is_dir()]
    if missing:
        sys.stderr.write(
            f'remote: not a directory: {", ".join(str(p) for p in missing)}\n',
        )
        return 2
    if shutil.which('gh') is None:
        sys.stderr.write(
            'remote: needs the GitHub CLI -- install `gh`, then run '
            '`gh auth login`.\n',
        )
        return 2

    now = datetime.now(UTC)
    skips = read_skips(skip_path())
    found = audit.find_repos(paths or audit.default_roots())
    wanted = [repo for repo in found if repo.name not in skips]
    repos = wanted if '--all-repos' in args else select_recent(wanted, now)

    def inspect_and_tick(path: Path) -> RepoRemote:
        row = inspect(path)
        progress.tick()
        return row

    with (
        Progress(len(repos), sys.stderr) as progress,
        ThreadPoolExecutor(max_workers=_WORKERS) as pool,
    ):
        rows = list(pool.map(inspect_and_tick, repos))
    output = (
        as_json(rows)
        if want_json
        else render(
            rows,
            now,
            colour=use_colour(sys.stdout),
            hidden=len(wanted) - len(repos),
            skipped=len(found) - len(wanted),
        )
    )
    sys.stdout.write(output + '\n')
    return 0


def main_cli() -> None:
    """Console-script entry point."""
    raise SystemExit(main())


if __name__ == '__main__':
    main_cli()
