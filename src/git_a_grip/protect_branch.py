"""Refuse a push straight onto the default branch.

Branch protection on GitHub is the real guard, but a private repo on a free
plan cannot have it -- the API will not even say whether it is on. This is
the guard that is left, run where GitHub's would have been: at the push. A
commit on a local `main` harms nothing until it leaves the machine, and
checking the push rather than the commit also catches `git push origin
feature:main`, which a commit-time check never sees. `--no-verify` walks
straight past it, which is why `gag remote` reports it as `pre-commit`
rather than as protection.

What is checked is the remote branch pre-commit says is being pushed to
(`PRE_COMMIT_REMOTE_BRANCH`); run by hand, outside a push, it falls back to
the branch checked out.

The protected branch is the one `origin/HEAD` names, so a repo whose default
is `trunk` needs no config; without that ref (a fresh `git init`, a clone
that never recorded it) it falls back to `main` and `master`. `--branch=`
replaces the default outright, once per branch.

A detached HEAD is no branch at all -- a rebase in progress, a CI checkout --
so by hand it always passes.
"""

from __future__ import annotations

import os
import subprocess
import sys

_FALLBACK = frozenset({'main', 'master'})
_FLAG = '--branch='


def _git(*args: str) -> str:
    return subprocess.run(  # noqa: S603 -- fixed argv, no shell
        ['git', *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


def default_branches() -> frozenset[str]:
    """The branch `origin/HEAD` points at, else `main` and `master`."""
    ref = _git('symbolic-ref', '--short', '-q', 'refs/remotes/origin/HEAD')
    _, _, branch = ref.partition('/')
    return frozenset({branch}) if branch else _FALLBACK


def main(argv: list[str]) -> int:
    """Exit 1 if HEAD is a protected branch, 2 on an argument it can't use."""
    unknown = [a for a in argv if not a.startswith(_FLAG)]
    if unknown:
        sys.stderr.write(
            f'protect-branch: unknown argument {unknown[0]!r}; '
            f'name branches as {_FLAG}NAME.\n',
        )
        return 2
    # An empty name would match a detached HEAD's empty branch.
    named = frozenset(filter(None, (a.removeprefix(_FLAG) for a in argv)))
    protected = named or default_branches()
    target = os.environ.get('PRE_COMMIT_REMOTE_BRANCH', '')
    current = (
        target.removeprefix('refs/heads/')
        if target
        else _git('symbolic-ref', '--short', '-q', 'HEAD')
    )
    if current not in protected:
        return 0
    sys.stderr.write(
        f'protect-branch: `{current}` is protected -- push a branch and '
        'open a PR.\n'
        '  git switch -c my-change && git push -u origin my-change\n'
        f'  git branch -f {current} origin/{current}   '
        '# then rewind the local copy\n'
        'To push here once anyway: SKIP=protect-branch git push ...\n',
    )
    return 1
