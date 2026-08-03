"""The installed version of this package, and how a repo pins it.

Two audiences need this string. `gag audit` prints it so the versions
it found in other repos have something to be compared *against*, and
`gag sync` writes it into those repos' configs. Both would otherwise have to
re-read `pyproject.toml`, which is not shipped in the wheel.

The tag format is commitizen's (`tag_format = "v$version"` in pyproject), so
a rev and a version differ only by a leading `v`. Everything here treats the
two as the same fact in two spellings.
"""

from __future__ import annotations

from importlib import metadata

DIST_NAME = 'git-a-grip'
REPO_URL = 'https://github.com/dannybrown37/git-a-grip'
UNKNOWN = '0+unknown'


def installed_version() -> str:
    """Return this package's version, or a placeholder if it has none.

    A source checkout that was never installed has no distribution metadata.
    That is a normal state for the repo itself, so it reports a placeholder
    rather than raising.
    """
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
