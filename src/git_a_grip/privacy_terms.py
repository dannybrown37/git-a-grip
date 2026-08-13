"""The store behind the `block-private-terms` hook: where the terms live.

A secret scanner finds credentials because credentials look like credentials
-- high entropy, a known prefix, a shape a regex can name. The strings this
guards against have none of that. An employer, a client, an internal
hostname, a street, a relative's name: ordinary words that are only sensitive
because of who typed them. No shipped ruleset will ever contain them, which
is why the terms are the user's and never the repo's.

That makes *where they live* the whole design. They cannot sit in the tree,
so the hook looks for them along a ladder, first hit winning:

1. `--terms-file=` in the hook's `args:`
2. `$GAG_PRIVACY_TERMS_FILE`
3. `$XDG_CONFIG_HOME/git-a-grip/privacy-terms` (`~/.config/...`)
4. `<repo>/.git/privacy-terms`

Rung 3 is the one people should use: one file, every repo on the machine
covered, set up once. Rung 4 exists because `.git/` cannot be committed by
accident, which makes it the right home for a term that belongs to exactly
one project -- and the wrong home for the rest, since deleting a clone
deletes the protection with no warning that it went.

The file is line-delimited text, read literally. It is never sourced or
evaluated: a config format that executes is a worse hazard than the one this
module exists to remove.

Permissions are enforced rather than suggested. A terms file the
rest of the machine can read is worse than no file at all -- the user
believes they are covered while the terms sit in the open -- so a loose mode
is a hard error, not a warning. Symlinks are followed first and judged at
the far end, because a link's own mode is meaninglessly 0o777 and the
exposure belongs to the file actually holding the words.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

ENV_VAR = 'GAG_PRIVACY_TERMS_FILE'
FILENAME = 'privacy-terms'
MIN_LENGTH = 3
# Below this, showing two characters either side of the mask would be most
# of the term.
_WIDE_ENOUGH_FOR_TWO = 8
# Anything a group or the world can do with the file. Owner-only is the
# only mode that makes the file worth keeping.
_TOO_OPEN = stat.S_IRWXG | stat.S_IRWXO


class PrivacyTermsError(Exception):
    """A terms file that cannot be trusted, or a term that cannot be kept."""


def git_dir() -> Path | None:
    """Return this repo's `.git` directory, or None outside a repo."""
    found = subprocess.run(
        ['git', 'rev-parse', '--absolute-git-dir'],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return Path(found) if found else None


def user_path() -> Path:
    """Return the one-per-machine terms file, whether or not it exists."""
    config = os.environ.get('XDG_CONFIG_HOME')
    root = Path(config) if config else Path.home() / '.config'
    return root / 'git-a-grip' / FILENAME


def repo_path() -> Path | None:
    """Return this repo's own terms file, or None outside a repo."""
    found = git_dir()
    return None if found is None else found / FILENAME


def default_path(*, repo: bool = False) -> Path:
    """Return where a newly added term should be written."""
    if not repo:
        return user_path()
    path = repo_path()
    if path is None:
        message = 'not inside a git repository'
        raise PrivacyTermsError(message)
    return path


def resolve(explicit: Path | None = None) -> Path | None:
    """Return the terms file in force here, or None if there is none.

    A path named outright comes back whether or not it exists: someone who
    wrote `--terms-file=` meant that file, and silently falling through to
    the next rung would leave them protected by terms they never chose.
    """
    if explicit is not None:
        return Path(explicit)
    from_env = os.environ.get(ENV_VAR)
    if from_env:
        return Path(from_env)
    for candidate in (user_path(), repo_path()):
        if candidate is not None and candidate.exists():
            return candidate
    return None


def _check_mode(path: Path) -> Path:
    """Return the real file behind `path`, refusing a too-open one."""
    real = path.resolve()
    mode = stat.S_IMODE(real.stat().st_mode)
    if mode & _TOO_OPEN:
        message = (
            f'{real} is readable beyond its owner (mode {mode:04o}).\n'
            f'These terms are the thing being protected. Run:\n'
            f'  chmod 600 {real}'
        )
        raise PrivacyTermsError(message)
    return real


def read(path: Path) -> list[str]:
    """Return the terms in `path`, or nothing if it is not there yet.

    A missing file is the unconfigured state, which every caller handles;
    an unreadable or over-shared one is a real problem and raises.
    """
    if not path.exists():
        return []
    real = _check_mode(path)
    try:
        text = real.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as error:
        message = f'cannot read {real}: {error}'
        raise PrivacyTermsError(message) from error
    lines = (line.strip() for line in text.splitlines())
    return [line for line in lines if line and not line.startswith('#')]


def write(path: Path, terms: list[str]) -> None:
    """Replace `path`'s contents with `terms`, atomically and privately.

    The write lands on a sibling temp file and is renamed over the target,
    so a write that dies partway leaves the old terms rather than a
    truncated file -- which would read as fewer terms and quietly stop
    matching. Symlinks are written *through*: someone whose config is
    symlinked out of a dotfiles repo means the file at the far end.
    """
    real = path.resolve() if path.is_symlink() else path
    real.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    body = ''.join(f'{term}\n' for term in terms)
    # mkstemp creates at 0o600 with no window at anything wider, which
    # chmod-after-the-fact could not promise.
    handle, temp = tempfile.mkstemp(dir=real.parent, prefix=f'.{real.name}.')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            stream.write(body)
        Path(temp).replace(real)
    except OSError as error:
        Path(temp).unlink(missing_ok=True)
        message = f'cannot write {real}: {error}'
        raise PrivacyTermsError(message) from error


def _validate(term: str, *, force: bool) -> str:
    cleaned = term.strip()
    if any(char in term for char in '\r\n'):
        message = f'a term cannot span lines: {mask(cleaned)!r}'
        raise PrivacyTermsError(message)
    if not cleaned:
        message = 'a term cannot be empty'
        raise PrivacyTermsError(message)
    if len(cleaned) < MIN_LENGTH and not force:
        # A two-character term matches half the tree, and a hook that cries
        # wolf gets deleted from the config -- taking the real terms with it.
        message = (
            f'{mask(cleaned)!r} is shorter than {MIN_LENGTH} characters and '
            f'would match nearly everything. Pass --force to keep it anyway.'
        )
        raise PrivacyTermsError(message)
    return cleaned


def add(path: Path, terms: list[str], *, force: bool = False) -> list[str]:
    """Append the terms not already held, returning the ones added."""
    wanted = [_validate(term, force=force) for term in terms]
    existing = read(path)
    seen = {term.casefold() for term in existing}
    added: list[str] = []
    for term in wanted:
        if term.casefold() in seen:
            continue
        seen.add(term.casefold())
        added.append(term)
    if added:
        write(path, [*existing, *added])
    return added


def remove(path: Path, terms: list[str]) -> tuple[list[str], list[str]]:
    """Drop the named terms, returning what went and what was not there."""
    targets = {term.strip().casefold() for term in terms}
    existing = read(path)
    kept = [term for term in existing if term.casefold() not in targets]
    removed = [term for term in existing if term.casefold() in targets]
    still_there = {term.casefold() for term in removed}
    missing = [
        term for term in terms if term.strip().casefold() not in still_there
    ]
    if removed:
        write(path, kept)
    return removed, missing


def mask(term: str) -> str:
    """Return a term with its middle hidden, for printing to a screen.

    Enough to recognise which of your own terms this is, not enough to be
    the leak. `gag privacy list` and the hook's own failures both go to a
    terminal, into scrollback, and often into a CI log.
    """
    if len(term) <= MIN_LENGTH:
        return '*' * len(term)
    edge = 1 if len(term) < _WIDE_ENOUGH_FOR_TWO else 2
    return f'{term[:edge]}{"*" * (len(term) - 2 * edge)}{term[-edge:]}'


def matches(text: str, terms: list[str], *, word: bool = False) -> list[str]:
    """Return the terms found in `text`, in the order they were given.

    Terms are literal strings a person typed, never patterns -- a term with
    a dot in it is a domain name, not a wildcard.
    """
    haystack = text.casefold()
    found: list[str] = []
    for term in terms:
        needle = term.casefold()
        if word:
            pattern = rf'(?<!\w){re.escape(needle)}(?!\w)'
            hit = re.search(pattern, haystack) is not None
        else:
            hit = needle in haystack
        if hit:
            found.append(term)
    return found
