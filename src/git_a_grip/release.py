"""Bump, tag and push as one command -- the ordering pre-push cannot have.

This replaces a pre-push hook that did the same work (removed in v0.3.0).
There, git had already chosen which sha to push before any hook ran, so a
commit created afterwards could only end two ways: cancel the push, or let
git push the superseded sha and watch it rejected as a non-fast-forward. Both
print `error: failed to push some refs` over a release that succeeded.

Run as a command instead, the order is simply right: bump first, push second,
exit 0. Nothing to cancel, nothing to explain away. Point whatever alias you
use for pushing at this, and a release stays one gesture.
"""

from __future__ import annotations

import subprocess
import sys

from git_a_grip import cz

# `cz bump` exit codes that mean "nothing to release", not "something broke".
NO_COMMITS_FOUND = 21
NONE_INCREMENT = 3
PROTECTED_DEFAULT = 'main'


def git(*args: str) -> subprocess.CompletedProcess[str]:
    """Run git with `args`, capturing output."""
    return subprocess.run(  # noqa: S603
        ['git', *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )


def current_branch() -> str:
    """Return the checked-out branch."""
    return git('rev-parse', '--abbrev-ref', 'HEAD').stdout.strip()


def is_dirty() -> bool:
    """Whether the working tree has uncommitted changes."""
    return bool(git('status', '--porcelain').stdout.strip())


def _push(branch: str, *extra: str) -> int:
    # --no-verify so any pre-push hook the repo still has wired cannot
    # re-enter this.
    pushed = git(
        'push',
        '--no-verify',
        '--follow-tags',
        *extra,
        'origin',
        branch,
    )
    if pushed.returncode != 0:
        sys.stderr.write(pushed.stderr)
    return pushed.returncode


USAGE = """\
gag release -- bump the version, tag it, and push, in that order.

  gag release              on main: bump, tag and push; elsewhere: just push
  gag release --any-branch release from the current branch, whatever it is
  gag release --help       show this

Configure what the bump rewrites via [tool.commitizen] in the repo.
"""


def check_args(args: list[str]) -> int | None:
    """Return an exit code if the args mean "do not release", else None."""
    if '--help' in args or '-h' in args:
        sys.stdout.write(USAGE)
        return 0
    # This command publishes. An argument it does not understand may well be
    # someone asking for something other than "release now", so refuse rather
    # than ignore it and push.
    unknown = [a for a in args if a != '--any-branch']
    if unknown:
        sys.stderr.write(
            f'release: unrecognised argument(s): {" ".join(unknown)}\n\n',
        )
        sys.stderr.write(USAGE)
        return 2
    return None


def main(argv: list[str] | None = None) -> int:
    """Bump if there is anything to release, then push. 0 means done."""
    args = sys.argv[1:] if argv is None else argv

    refused = check_args(args)
    if refused is not None:
        return refused

    branch = current_branch()
    if branch != PROTECTED_DEFAULT and '--any-branch' not in args:
        # Not the release branch: just push, so this can stand in for
        # `git push` everywhere without surprising anyone on a feature branch.
        return _push(branch)

    if is_dirty():
        sys.stderr.write(
            'release: working tree is dirty, refusing to bump. '
            'Commit or stash first.\n',
        )
        return 1

    return _bump_and_push(branch)


def _bump_and_push(branch: str) -> int:
    result = cz.run('bump', '--yes', '--no-verify')
    if result.returncode in {NO_COMMITS_FOUND, NONE_INCREMENT}:
        sys.stdout.write('No version-bumping commits since the last tag.\n')
        return _push(branch)
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        sys.stderr.write(
            f'release: cz bump failed (exit {result.returncode}).\n',
        )
        return result.returncode

    version = cz.run('version', '-p').stdout.strip()
    code = _push(branch)
    if code != 0:
        sys.stderr.write(
            f'release: bumped to v{version} locally but the push failed. '
            'Fix the remote and run `git push --follow-tags`.\n',
        )
        return code

    sys.stdout.write(f'Released v{version} (commit + tag pushed).\n')
    return 0


def main_cli() -> None:
    """Console-script entry point."""
    raise SystemExit(main())


if __name__ == '__main__':
    main_cli()
