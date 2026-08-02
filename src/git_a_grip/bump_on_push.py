"""pre-push: turn the conventional commits since the last tag into a version.

Runs `cz bump`, which rewrites whatever `version_files`/`version_provider`
the consuming repo configured, writes CHANGELOG.md and creates a tag.

The catch: that bump commit does not exist yet when git works out what to
push, so pushing normally would ship the pre-bump sha and leave the version
artifacts behind. This hook therefore pushes the bumped ref itself and then
fails the original push. Nothing is lost -- the branch is fully pushed by the
time the error appears -- but git prints its own failure line last, so the
explanation goes to stderr just above it.
"""

from __future__ import annotations

import subprocess
import sys

from git_a_grip import cz

# `cz bump` exit codes that mean "nothing to release", not "something broke".
NO_COMMITS_FOUND = 21
NONE_INCREMENT = 3
_PROTECTED_DEFAULT = 'main'


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ['git', *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )


def current_branch() -> str:
    """Return the branch being pushed."""
    return _git('rev-parse', '--abbrev-ref', 'HEAD').stdout.strip()


def is_dirty() -> bool:
    """Whether the working tree has uncommitted changes."""
    return bool(_git('status', '--porcelain').stdout.strip())


def main() -> int:
    """Bump, tag and push; or get out of the way."""
    branch = current_branch()
    if branch != _PROTECTED_DEFAULT:
        return 0

    if is_dirty():
        sys.stderr.write(
            'pre-push: working tree is dirty, refusing to bump. '
            'Commit or stash first.\n',
        )
        return 1

    result = cz.run('bump', '--yes')
    if result.returncode in {NO_COMMITS_FOUND, NONE_INCREMENT}:
        sys.stdout.write(
            'pre-push: no version-bumping commits since the last tag, '
            'pushing as-is.\n',
        )
        return 0
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        sys.stderr.write(
            f'pre-push: cz bump failed (exit {result.returncode}).\n',
        )
        return result.returncode

    sys.stdout.write(result.stdout)
    version = cz.run('version', '-p').stdout.strip()

    # --no-verify so this hook does not re-enter itself.
    pushed = _git(
        'push',
        '--no-verify',
        '--follow-tags',
        'origin',
        branch,
    )
    if pushed.returncode != 0:
        sys.stderr.write(pushed.stderr)
        sys.stderr.write(
            f'pre-push: bumped to v{version} locally but the push failed. '
            'Fix the remote and run `git push --follow-tags`.\n',
        )
        return pushed.returncode

    sys.stderr.write(
        f'\npre-push: bumped to v{version} and pushed it '
        '(commits + tag) already.\n'
        'The original push is being cancelled because it pointed at the '
        'pre-bump\ncommit -- nothing is missing, your branch is fully '
        'pushed. Nothing else to do.\n',
    )
    return 1


def main_cli() -> None:
    """Console-script entry point."""
    raise SystemExit(main())


if __name__ == '__main__':
    main_cli()
