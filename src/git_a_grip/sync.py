"""Pin every local repo's hooks to one version, in one command.

`pre-commit-audit` ends with a list of repos pinning four different revs of
this package, and no way to act on it. Fixing that by hand is a `cd`, an
edit and a `git commit` per repo -- so it does not get done, and the fleet
drifts until a hook changes behaviour and only some repos notice.

    hook-sync                    show what would change (default: dry run)
    hook-sync --write            rewrite the configs
    hook-sync --to v0.4.0        pin to a version other than the installed
    hook-sync --repo URL         sync some other hook source instead
    hook-sync --latest           take the target from the source's git tags
    hook-sync ~/projects ~/work  trees to scan (default: this repo's parent)

The rewrite is textual, not a YAML round-trip: `yaml.safe_load` loses the
comments and the key order a hand-written config is full of, and handing
somebody back a reformatted config is a worse trade than the one line they
wanted changed. Only the `rev:` line belonging to a matched `repo:` block is
touched, and only when its value actually differs.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from git_a_grip import audit, version

USAGE = """\
hook-sync -- pin one hook source to one rev across every local repo.

  hook-sync [PATH ...]     trees to scan (default: this repo's parent)
  hook-sync --write        apply the changes (default is a dry run)
  hook-sync --to REV       target rev (default: the installed version)
  hook-sync --repo URL     hook source to sync (default: git-a-grip)
  hook-sync --latest       resolve the target from the source's git tags
  hook-sync --help         show this
"""

# `  - repo: https://github.com/...` followed, within the block, by `rev:`.
_REPO_LINE = re.compile(r'^(\s*)-\s+repo:\s*(\S+)\s*$')
_REV_LINE = re.compile(r'^(\s*)rev:\s*(\S+)\s*(#.*)?$')
_TAG_REF = re.compile(r'refs/tags/(v?\d+(?:\.\d+)*)$')


@dataclass
class Change:
    """One repo's config, and the rev move it needs."""

    path: Path
    source: str
    old: str
    new: str

    @property
    def name(self) -> str:
        """The name of the repo holding the config."""
        return self.path.parent.name


def matches_source(candidate: str, wanted: str) -> bool:
    """Whether a config's `repo:` names the source we are syncing.

    Compared on the trailing path segments so that the ssh, https and
    `.git`-suffixed spellings of one GitHub repo all count as the same
    source -- which they are.
    """
    return _slug(candidate) == _slug(wanted) and bool(_slug(wanted))


def _slug(url: str) -> str:
    trimmed = url.rstrip('/').removesuffix('.git')
    parts = re.split(r'[/:]', trimmed)
    return '/'.join(parts[-2:]).lower() if len(parts) >= 2 else ''  # noqa: PLR2004


def rewrite(text: str, source: str, new_rev: str) -> tuple[str, str]:
    """Return the config with `source` pinned to `new_rev`, and the old rev.

    The old rev comes back empty when nothing matched -- either the source
    is absent or it is already at the target.
    """
    lines = text.splitlines(keepends=True)
    in_block = False
    old = ''
    for index, line in enumerate(lines):
        repo_match = _REPO_LINE.match(line)
        if repo_match:
            in_block = matches_source(repo_match.group(2), source)
            continue
        if not in_block:
            continue
        rev_match = _REV_LINE.match(line)
        if not rev_match:
            # Any other key at this level is still inside the block; only a
            # new `- repo:` ends it, and that is handled above.
            continue
        indent, current, comment = rev_match.groups()
        in_block = False  # one rev per block; the rest of it is hooks
        if current == new_rev:
            continue
        old = current
        suffix = f'  {comment}' if comment else ''
        lines[index] = f'{indent}rev: {new_rev}{suffix}\n'
    return (''.join(lines), old) if old else (text, '')


def plan(roots: list[Path], source: str, new_rev: str) -> list[Change]:
    """Find every config that pins `source` to something other than target."""
    changes = []
    for repo in audit.find_repos(roots):
        config = repo / audit.CONFIG_NAME
        try:
            text = config.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        _, old = rewrite(text, source, new_rev)
        if old:
            changes.append(
                Change(path=config, source=source, old=old, new=new_rev),
            )
    return changes


def apply(changes: list[Change]) -> list[Change]:
    """Write each planned change, returning the ones that landed."""
    written = []
    for change in changes:
        text = change.path.read_text(encoding='utf-8')
        updated, old = rewrite(text, change.source, change.new)
        if not old:
            continue  # changed underneath us; leave it for the next run
        change.path.write_text(updated, encoding='utf-8')
        written.append(change)
    return written


def latest_tag(source: str) -> str:
    """Ask the remote for its highest version tag, or '' if it cannot say."""
    result = subprocess.run(  # noqa: S603
        ['git', 'ls-remote', '--tags', '--refs', source],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ''
    tags = [
        match.group(1)
        for line in result.stdout.splitlines()
        if (match := _TAG_REF.search(line.strip()))
    ]
    if not tags:
        return ''
    return max(tags, key=version.parts)


def render(
    changes: list[Change],
    source: str,
    rev: str,
    *,
    wrote: bool,
) -> str:
    """Describe the plan, or what was done to it."""
    verb = 'Pinned' if wrote else 'Would pin'
    if not changes:
        return f'Every repo pinning {source} is already at {rev}.'
    lines = [f'{verb} {source} to {rev} in {len(changes)} repo(s):', '']
    lines += [
        f'  {change.name:<28} {change.old:<12} -> {change.new}'
        for change in sorted(changes, key=lambda c: c.name)
    ]
    if not wrote:
        lines += ['', 'Re-run with --write to apply.']
    return '\n'.join(lines)


def _flag_value(args: list[str], flag: str) -> str | None:
    prefix = f'{flag}='
    for index, arg in enumerate(args):
        if arg.startswith(prefix):
            return arg[len(prefix) :]
        if arg == flag and index + 1 < len(args):
            return args[index + 1]
    return None


def _consumed(args: list[str], flags: tuple[str, ...]) -> set[int]:
    taken: set[int] = set()
    for index, arg in enumerate(args):
        if arg.startswith('-'):
            taken.add(index)
            if arg in flags and index + 1 < len(args):
                taken.add(index + 1)
    return taken


def resolve_target(args: list[str], source: str) -> tuple[str, str]:
    """Return the rev to pin to and an error message if it cannot be found."""
    explicit = _flag_value(args, '--to')
    if explicit:
        return version.as_rev(explicit), ''
    if '--latest' in args:
        tag = latest_tag(source)
        if not tag:
            return '', f'sync: no version tags found at {source}\n'
        return version.as_rev(tag), ''
    installed = version.installed_version()
    if installed == version.UNKNOWN:
        return '', (
            'sync: this package is not installed, so it has no version to '
            'sync to. Pass --to REV or --latest.\n'
        )
    return version.as_rev(installed), ''


def main(argv: list[str] | None = None) -> int:
    """Plan (and optionally apply) a rev sync across the local repos."""
    args = sys.argv[1:] if argv is None else argv
    if '--help' in args or '-h' in args:
        sys.stdout.write(USAGE)
        return 0
    source = _flag_value(args, '--repo') or version.REPO_URL
    rev, error = resolve_target(args, source)
    if error:
        sys.stderr.write(error)
        return 2

    taken = _consumed(args, ('--to', '--repo'))
    paths = [Path(a) for i, a in enumerate(args) if i not in taken]
    missing = [p for p in paths if not p.is_dir()]
    if missing:
        sys.stderr.write(
            f'sync: not a directory: {", ".join(str(p) for p in missing)}\n',
        )
        return 2

    changes = plan(paths or audit.default_roots(), source, rev)
    wrote = '--write' in args
    if wrote:
        changes = apply(changes)
    sys.stdout.write(render(changes, source, rev, wrote=wrote) + '\n')
    return 0


def main_cli() -> None:
    """Console-script entry point."""
    raise SystemExit(main())


if __name__ == '__main__':
    main_cli()
