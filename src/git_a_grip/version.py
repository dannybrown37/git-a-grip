"""The installed version of this package, and how a repo pins it.

Two audiences need this string. `gag audit` prints it so the versions
it found in other repos have something to be compared *against*, and
`gag sync` writes it into those repos' configs. Neither can afford to be
wrong about it: the answer ends up pinned in someone else's repo.

The wheel ships no `pyproject.toml`, so an installed copy has only its
distribution metadata to go on. A checkout has both, and they disagree
whenever the editable install is older than the last bump -- see
`installed_version` for which one wins and why.

The tag format is commitizen's (`tag_format = "v$version"` in pyproject), so
a rev and a version differ only by a leading `v`. Everything here treats the
two as the same fact in two spellings.
"""

from __future__ import annotations

import tomllib
from importlib import metadata
from pathlib import Path

DIST_NAME = 'git-a-grip'
REPO_URL = 'https://github.com/dannybrown37/git-a-grip'
UNKNOWN = '0+unknown'

# src/git_a_grip/version.py -> the checkout root, if this is a checkout at
# all. A wheel unpacked into site-packages has no pyproject.toml up there.
_SOURCE_ROOT = Path(__file__).resolve().parents[2]


def version_from_source(root: Path) -> str | None:
    """Return the version a git-a-grip checkout at `root` declares.

    `None` for anything that is not this package's own source tree -- a
    missing, foreign, or malformed `pyproject.toml`. Reporting a version is
    never the caller's real errand, so nothing here raises.
    """
    try:
        data = tomllib.loads(root.joinpath('pyproject.toml').read_text())
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    project = data.get('project', {})
    if project.get('name') != DIST_NAME:
        return None
    declared = project.get('version')
    return declared if isinstance(declared, str) else None


def installed_version() -> str:
    """Return this package's version, or a placeholder if it has none.

    A checkout's own `pyproject.toml` outranks the distribution metadata,
    because an editable install's dist-info is only as fresh as the last
    `uv sync` -- and `cz bump` lands in CI, so it is routinely a release
    behind. That stale number is not a local cosmetic problem: `gag sync`
    writes this string into *other* repos' pins, and the `gag hooks` block
    embeds it in the README a person copies from.

    A source checkout that was never installed has no distribution metadata
    either. That is a normal state for the repo itself, so it reports a
    placeholder rather than raising.
    """
    from_source = version_from_source(_SOURCE_ROOT)
    if from_source is not None:
        return from_source
    try:
        return metadata.version(DIST_NAME)
    except metadata.PackageNotFoundError:
        return UNKNOWN


def as_rev(version: str) -> str:
    """Return the git tag that a given version was released under."""
    return version if version.startswith('v') else f'v{version}'


def as_version(rev: str) -> str:
    """Return the version a git tag names, dropping the leading `v`."""
    return rev[1:] if rev.startswith('v') else rev


def parts(version: str) -> tuple[int, ...]:
    """Return the leading numeric components of a version or tag."""
    numbers: list[int] = []
    for chunk in as_version(version).split('.'):
        # Leading digits only: `3rc1` is the 3rd component, not the 31st.
        digits = ''
        for char in chunk:
            if not char.isdigit():
                break
            digits += char
        if not digits:
            break
        numbers.append(int(digits))
    return tuple(numbers)


def compare(left: str, right: str) -> int:
    """Order two versions: -1 if left is older, 0 if equal, 1 if newer.

    Only the leading numeric components are compared. A rev this cannot
    parse -- a branch name, a sha, an empty string -- compares as older than
    anything numeric, which is the answer that makes `gag sync` offer to
    pin it.
    """
    first, second = parts(left), parts(right)
    if first == second:
        return 0
    return -1 if first < second else 1
