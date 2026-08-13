"""Block a commit that adds a line matching one of your private terms.

gitleaks and friends find credentials, because a credential looks like one:
high entropy, a known prefix, a shape a regex can name. The strings this
catches have none of that. An employer, a client, an internal hostname, a
relative's name, a street -- ordinary words, sensitive only because of who
typed them. No shipped ruleset will ever contain yours, so the terms come
from a file only you have; `privacy_terms` documents where it lives and why
it is never in the repo.

Only *added* lines are read. A term already in the history is a different
problem and not one a commit hook can solve, and flagging it on every commit
that touches the file would train the author to reach for `--no-verify`,
which is the outcome this is trying to avoid.

Unconfigured, it warns once and passes. That is deliberate: the hook ships
in a shared config that lands on machines whose owner has not set up a terms
file, and a hard failure there gets the hook deleted from the config --
taking the protection away from everyone who *had* configured it. A file
that exists but is world-readable is the opposite case and does fail, since
believing you are covered while the terms sit in the open is worse than
knowing you are not.

Nothing here prints the offending line. The hook's own output goes to a
terminal, into scrollback, and in CI into a log with a URL -- publishing the
match would leak exactly what the match just caught. It reports the file,
the line number, and a masked term; the author has the line in front of
them.

Exits non-zero, and does not rewrite anything. Which of the two -- the line
or the term -- is wrong is a judgement only the author can make.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from git_a_grip import privacy_terms
from git_a_grip.privacy_terms import PrivacyTermsError

USAGE = """\
usage: privacy-terms [--terms-file=PATH] [--word] [file ...]

Scans the staged diff for terms in your privacy-terms file. With no files,
the whole staged diff. See `gag privacy --help` to manage the terms.
"""


def added_lines(paths: list[str]) -> list[tuple[str, int, str]]:
    """Return (file, line number, text) for every line this commit adds.

    Reads a zero-context diff rather than the files themselves, so a term
    that was already committed stays the author's business and only what
    this commit introduces is judged.
    """
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            'git',
            '-c',
            'core.quotePath=false',
            'diff',
            '--cached',
            '-U0',
            '--no-color',
            '--diff-filter=ACM',
            '--',
            *paths,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    found: list[tuple[str, int, str]] = []
    name = ''
    number = 0
    for line in result.stdout.splitlines():
        if line.startswith('+++ '):
            target = line[4:].strip()
            # `+++ b/path`, or /dev/null for a delete that the filter above
            # should already have dropped.
            name = target[2:] if target.startswith('b/') else target
        elif line.startswith('@@'):
            number = _hunk_start(line)
        elif line.startswith('+') and not line.startswith('+++'):
            found.append((name, number, line[1:]))
            number += 1
    return found


def _hunk_start(header: str) -> int:
    """Return the first new-file line number a `@@ -a,b +c,d @@` covers."""
    try:
        after = header.split('+', 1)[1].split(' ', 1)[0]
        return int(after.split(',', 1)[0])
    except (IndexError, ValueError):
        return 0


def _report(hits: list[tuple[str, int, str]]) -> None:
    for name, number, term in hits:
        sys.stderr.write(
            f'{name}:{number}: adds a privacy term '
            f'({privacy_terms.mask(term)})\n',
        )
    sys.stderr.write(
        f'\n{len(hits)} blocked. Remove the content, or drop the term with '
        f'`gag privacy remove`.\nThe terms are in '
        f'{privacy_terms.resolve() or "your terms file"}.\n',
    )


def main(argv: list[str] | None = None) -> int:
    """Fail the commit if it adds a private term. 0 means it did not."""
    args = sys.argv[1:] if argv is None else argv
    if '--help' in args or '-h' in args:
        sys.stdout.write(USAGE)
        return 0
    word = '--word' in args
    named = [a for a in args if a.startswith('--terms-file=')]
    explicit = Path(named[-1].split('=', 1)[1]) if named else None
    paths = [a for a in args if not a.startswith('-')]

    try:
        path = privacy_terms.resolve(explicit)
        terms = privacy_terms.read(path) if path is not None else []
    except PrivacyTermsError as error:
        sys.stderr.write(f'privacy-terms: {error}\n')
        return 1

    if not terms:
        # Loud enough to notice, passing so that an unconfigured machine
        # does not make this the hook everyone removes.
        sys.stderr.write(
            'privacy-terms: no terms configured — this commit was not '
            'checked. Set them up with `gag privacy add`.\n',
        )
        return 0

    hits = [
        (name, number, term)
        for name, number, text in added_lines(paths)
        for term in privacy_terms.matches(text, terms, word=word)
    ]
    if not hits:
        return 0
    _report(hits)
    return 1


def main_cli() -> None:
    """Console-script entry point."""
    raise SystemExit(main())


if __name__ == '__main__':
    main_cli()
