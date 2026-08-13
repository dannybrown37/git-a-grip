"""`gag privacy`: manage the terms the `block-private-terms` hook matches on.

The terms are the thing being protected, which makes every part of this
command's interface a privacy decision rather than a convenience one:

- `list` masks by default. A command that prints your terms in full, into
  scrollback and onto whatever screen is being shared, defeats the file it
  is reading from. `--reveal` is there for when you mean it.
- `add` with no term prompts, and the prompt *does* echo. These are the
  strings that identify you -- an employer, a client, a name -- not
  credentials nobody may ever see, and a term with a typo in it protects
  nothing while reading as though it does. Seeing what you typed is worth
  more here than hiding it from the screen. Passing the term as an argument
  still works and is what a script should do, at the cost of a line in
  `~/.bash_history`.
- Every prompt and picker here is a layer over a flag that already worked,
  and every interactive run ends by printing the argument form of what just
  happened. The interactive path is for the first time; the echoed line is
  for the fourth. Off a tty nothing prompts -- it says which argument was
  missing and exits, rather than blocking a CI job on a question no one is
  reading.
- There is no `edit`. Handing the file to `$EDITOR` means vim writes
  `.privacy-terms.swp` beside it at whatever mode the umask says, holding
  exactly the strings we are guarding. `gag privacy path` prints the
  location for anyone who wants to own that themselves.

Where the terms live, and why, is in `privacy_terms`.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

from git_a_grip import pick, privacy_terms, version
from git_a_grip.privacy_terms import PrivacyTermsError

USAGE = """\
usage: gag privacy [action] [options]

actions:
  status            Report the terms file in force, and how many
                    terms it holds
  add [term ...]    Add terms; prompts, one per line, when none are given
  remove [term ...] Remove terms; offers the ones you have when none
                    are given
  list              List the terms, masked
  path              Print the path terms are read from, and nothing else
  check [file]      Scan a file against the terms; offers the repo's
                    files on a terminal, reads stdin off one

options:
  --terms-file=PATH  Use this file rather than the usual search
  --repo             Write to this repo's .git/privacy-terms, not the
                     one-per-machine file
  --reveal           `list` prints terms in full, not masked
  --word             `check` requires a word boundary around a match
  --force            `add` keeps a term shorter than 3 characters
  --version          Print the git-a-grip version

With no action at all this prints the status, then offers the actions --
`fzf` if you have it, a numbered list if you don't. Set GAG_NO_FZF=1 to
always get the numbered list. Every prompt is skippable by passing the
argument, and an interactive run ends by printing the line that would have
skipped it. Off a terminal nothing prompts.

Terms are read from the first of: --terms-file, $GAG_PRIVACY_TERMS_FILE,
$XDG_CONFIG_HOME/git-a-grip/privacy-terms, then <repo>/.git/privacy-terms.
"""

ACTION_HELP = {
    'status': 'status  — which terms file is in force, and how full it is',
    'add': 'add     — add a term (prompts, one per line)',
    'remove': 'remove  — remove a term (pick from the ones you have)',
    'list': 'list    — show the terms, masked',
    'check': 'check   — scan a file for terms, without committing',
    'path': 'path    — print the terms file path, and nothing else',
}
ACTIONS = tuple(ACTION_HELP)


class _Options:
    """The flags, split out from the words the action operates on."""

    def __init__(self, args: list[str]) -> None:
        self.terms_file: Path | None = None
        self.repo = False
        self.reveal = False
        self.word = False
        self.force = False
        self.rest: list[str] = []
        self.unknown: list[str] = []
        self.given: list[str] = []
        for arg in args:
            if arg.startswith('-') and arg != '-':
                self.given.append(arg)
            if arg.startswith('--terms-file='):
                self.terms_file = Path(arg.split('=', 1)[1])
            elif arg == '--repo':
                self.repo = True
            elif arg == '--reveal':
                self.reveal = True
            elif arg == '--word':
                self.word = True
            elif arg == '--force':
                self.force = True
            elif arg.startswith('-') and arg != '-':
                self.unknown.append(arg)
            else:
                self.rest.append(arg)


def _write_target(options: _Options) -> Path:
    """Return the file `add` and `remove` should change.

    A write lands on the file already in force, not on whichever rung the
    ladder would have created -- adding a term to a fresh user file while a
    `.git` one is what the hook reads would leave the term inert, and
    creating a user file that outranks an existing `.git` one would quietly
    drop every term it held. `--repo` is the way to mean the other file.
    """
    if options.repo:
        return privacy_terms.default_path(repo=True)
    found = privacy_terms.resolve(options.terms_file)
    return found if found is not None else privacy_terms.user_path()


def _replay(options: _Options, action: str, *words: str) -> None:
    """Print the fully-argumented form of the run that just happened.

    A guided run is a pleasure once and a chore on the fourth iteration, so
    the last thing an interactive run does is hand over the one-liner that
    skips the guiding. It goes to stderr: `gag privacy path` is meant to be
    substituted into another command, and this must not land in it.
    """
    line = ' '.join(
        shlex.quote(part)
        for part in ['gag', 'privacy', action, *options.given, *words]
    )
    sys.stderr.write(f'\nNext time, in one line:\n  {line}\n')


def _tracked_files() -> list[str]:
    """Return the repo's tracked files, or nothing outside a repo."""
    result = subprocess.run(
        ['git', 'ls-files'],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line]


def _prompt_terms() -> list[str]:
    """Read terms from a tty, one per line, echoed so typos are visible.

    An argument is remembered by the shell; a prompt is not. Off a tty this
    refuses rather than reading a pipe, so a script that forgot its
    arguments fails loudly instead of hanging or storing a blank line.
    """
    sys.stderr.write('Enter a term per line, blank line to finish.\n')
    terms: list[str] = []
    while True:
        entry = pick.ask('term: ', missing='the terms as arguments')
        if not entry:
            return terms
        terms.append(entry)


def _status(options: _Options) -> int:
    path = privacy_terms.resolve(options.terms_file)
    if path is None:
        sys.stdout.write(
            'privacy: no terms file — nothing is being checked.\n'
            f'Add one with:\n  gag privacy add\n'
            f'It will be created at {privacy_terms.user_path()}\n',
        )
        return 0
    terms = privacy_terms.read(path)
    plural = '' if len(terms) == 1 else 's'
    sys.stdout.write(f'{path}\n{len(terms)} term{plural}\n')
    if not terms:
        sys.stdout.write(
            'The file is empty — nothing is being checked.\n'
            'Add terms with:\n  gag privacy add\n',
        )
    return 0


def _add(options: _Options) -> int:
    prompted = not options.rest
    terms = options.rest or _prompt_terms()
    if not terms:
        sys.stdout.write(USAGE)
        return 0
    path = _write_target(options)
    added = privacy_terms.add(path, terms, force=options.force)
    # The terms never go back to the terminal, so report the count and the
    # file: enough to know it worked, nothing to read over a shoulder.
    skipped = len(terms) - len(added)
    sys.stdout.write(f'Added {len(added)} to {path}\n')
    if skipped:
        sys.stdout.write(f'{skipped} already there\n')
    if prompted and added:
        # The terms were just typed, in the open, by the person reading
        # this line -- so the replayable form may hold them. `list` and the
        # hook's own output, which go to screens and CI logs, still mask.
        _replay(options, 'add', *added)
    return 0


def _pick_terms(path: Path) -> list[str]:
    """Offer the terms actually in the file, since they are what can go.

    Typing a term to remove it is guesswork against casing and spelling
    you set up months ago; a wrong guess reports "not found" and leaves
    the file exactly as it was. The list is shown in full here -- you
    cannot choose between things you cannot read -- which is why this
    path is the interactive one and never the scripted one.
    """
    terms = privacy_terms.read(path)
    if not terms:
        sys.stderr.write(f'privacy: no terms in {path}\n')
        return []
    return pick.choose(
        terms,
        prompt='remove: ',
        missing='the terms as arguments',
        multi=True,
    )


def _remove(options: _Options) -> int:
    path = _write_target(options)
    wanted = options.rest or _pick_terms(path)
    if not wanted:
        return 0
    removed, missing = privacy_terms.remove(path, wanted)
    sys.stdout.write(f'Removed {len(removed)} from {path}\n')
    if missing:
        sys.stderr.write(f'{len(missing)} not found\n')
    if not options.rest and removed:
        _replay(options, 'remove', *removed)
    return 0


def _list(options: _Options) -> int:
    path = privacy_terms.resolve(options.terms_file)
    if path is None:
        return _status(options)
    for term in privacy_terms.read(path):
        shown = term if options.reveal else privacy_terms.mask(term)
        sys.stdout.write(f'{shown}\n')
    return 0


def _path(options: _Options) -> int:
    path = privacy_terms.resolve(options.terms_file)
    if path is None:
        sys.stderr.write('privacy: no terms file\n')
        return 1
    sys.stdout.write(f'{path}\n')
    return 0


def _pick_file() -> str | None:
    """Return the file to scan, or None if the user picked nothing.

    `check` with no argument means stdin, which on a terminal is a command
    that sits there looking like it hung. On a tty the tracked files are
    offered instead; declining the picker ends the run rather than falling
    back to the read that would have hung.
    """
    if not pick.interactive():
        return '-'
    tracked = _tracked_files()
    if not tracked:
        return pick.ask('file to check: ', missing='a file') or None
    chosen = pick.choose(tracked, prompt='check: ', missing='a file')
    return chosen[0] if chosen else None


def _check(options: _Options) -> int:
    path = privacy_terms.resolve(options.terms_file)
    terms = privacy_terms.read(path) if path is not None else []
    if not terms:
        sys.stderr.write('privacy: no terms — nothing to check against\n')
        return 0
    name = options.rest[0] if options.rest else _pick_file()
    if name is None:
        return 0
    if name == '-':
        text = sys.stdin.read()
    else:
        try:
            text = Path(name).read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as error:
            sys.stderr.write(f'privacy: cannot read {name}: {error}\n')
            return 2
    found = 0
    for number, line in enumerate(text.splitlines(), start=1):
        for term in privacy_terms.matches(line, terms, word=options.word):
            # Masked, and without the line: this output goes to a terminal
            # and often to a CI log, and echoing the hit would publish the
            # thing the match just caught.
            sys.stdout.write(
                f'{name}:{number}: matches {privacy_terms.mask(term)}\n',
            )
            found += 1
    if not options.rest and name != '-':
        # Printed after the hits, and printed whether or not there were
        # any: a scan that failed is the one most likely to be re-run.
        _replay(options, 'check', name)
    return 1 if found else 0


_ACTIONS = {
    'status': _status,
    'add': _add,
    'remove': _remove,
    'list': _list,
    'path': _path,
    'check': _check,
}
_SELF_REPLAYING = ('add', 'remove', 'check')


def _no_action(options: _Options) -> int:
    """Answer a bare `gag privacy`: say where things stand, then offer to act.

    A bare run is how someone finds out what this command does, so it
    answers with the state of the terms file first and the actions second.
    Off a tty the actions are printed rather than offered -- usage text is
    a useful answer to a script, a picker is not.
    """
    status = _status(options)
    if not pick.interactive():
        sys.stdout.write(f'\n{USAGE}')
        return status
    chosen = pick.choose(
        list(ACTION_HELP.values()),
        prompt='gag privacy: ',
        missing='an action',
    )
    if not chosen:
        return status
    name = chosen[0].split()[0]
    code = _ACTIONS[name](options)
    if name not in _SELF_REPLAYING:
        # The others echo their own line once they know the terms or the
        # file involved, and two "next time" blocks in one run is noise.
        _replay(options, name)
    return code


def _early_exit(args: list[str]) -> int | None:
    """Answer --help/--version before anything else can fail on parsing."""
    if '--help' in args or '-h' in args:
        sys.stdout.write(USAGE)
        return 0
    if '--version' in args or '-V' in args:
        # The version belongs to `gag`, but nobody should have to know
        # which level of a command tree owns the flag they just typed.
        sys.stdout.write(f'{version.installed_version()}\n')
        return 0
    return None


def main(argv: list[str] | None = None) -> int:
    """Run an action against the terms file. 0 means it did what was asked."""
    args = sys.argv[1:] if argv is None else argv
    early = _early_exit(args)
    if early is not None:
        return early

    try:
        return _dispatch(args)
    except PrivacyTermsError as error:
        sys.stderr.write(f'privacy: {error}\n')
        return 2
    except pick.NotInteractiveError as error:
        sys.stderr.write(f'privacy: {error}\n\n{USAGE}')
        return 2


def _dispatch(args: list[str]) -> int:
    """Turn parsed arguments into exactly one action call."""
    options = _Options(args)
    if options.unknown:
        sys.stderr.write(
            f'privacy: unknown option: {options.unknown[0]}\n\n{USAGE}',
        )
        return 2

    # Flags are pulled out first, so `--repo add x` and `add --repo x` are
    # the same command. Only the leading word is read as the action; a term
    # that happens to be spelled `list` is still a term.
    name = ''
    if options.rest:
        name, *options.rest = options.rest
    if not name:
        return _no_action(options)
    if name not in _ACTIONS:
        sys.stderr.write(f'privacy: unknown action: {name}\n\n')
        sys.stderr.write(USAGE)
        return 2

    return _ACTIONS[name](options)


def main_cli() -> None:
    """Console-script entry point."""
    raise SystemExit(main())


if __name__ == '__main__':
    main_cli()
