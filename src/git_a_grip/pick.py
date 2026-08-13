"""Interactive selection, for commands a person runs by hand.

Every prompt here is a convenience laid over a flag that already worked. A
command must stay drivable with arguments alone, so this module never
invents an answer: off a tty it raises, and the caller turns that into a
message naming the argument that was missing. A prompt that quietly reads a
pipe is how a CI job hangs for its whole timeout with nothing in the log.

`fzf` is used when it is on PATH because picking beats typing a value blind,
but it is never required -- the numbered fallback is the same list, and the
same answer, for a machine that does not have it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

NO_FZF = 'GAG_NO_FZF'


class NotInteractiveError(Exception):
    """Asked for input where there is nobody to answer."""


def interactive() -> bool:
    """Report whether there is a human on the other end of this run."""
    return sys.stdin.isatty() and sys.stderr.isatty()


def _require_tty(missing: str) -> None:
    if not interactive():
        message = f'not a tty: pass {missing}'
        raise NotInteractiveError(message)


def ask(prompt: str, *, missing: str) -> str:
    """Read one line, or raise naming the argument that would have done.

    Prompts go to stderr and the answer is echoed, so a command whose
    stdout is being piped still shows its question and stays pipeable.
    """
    _require_tty(missing)
    sys.stderr.write(prompt)
    sys.stderr.flush()
    try:
        return input().strip()
    except EOFError:
        return ''


def _with_fzf(options: list[str], *, prompt: str, multi: bool) -> list[str]:
    command = [
        'fzf',
        f'--prompt={prompt}',
        '--height=40%',
        '--reverse',
    ]
    if multi:
        command.append('--multi')
    # Only stdout is taken. fzf draws its whole interface on stderr and
    # reads keys from /dev/tty, so capturing stderr leaves a live picker
    # painting into a pipe -- a blank terminal that reads as a hang.
    result = subprocess.run(  # noqa: S603
        command,
        input='\n'.join(options),
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    # Any non-zero exit is a decline -- escape, ^C, or no match. None of
    # those are errors, they are the user saying "not this one".
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line]


def _numbered(options: list[str], *, prompt: str, multi: bool) -> list[str]:
    for number, option in enumerate(options, start=1):
        sys.stderr.write(f'  {number}) {option}\n')
    hint = 'numbers, comma-separated' if multi else 'number'
    answer = ask(f'{prompt}({hint}, blank to cancel) ', missing='the value')
    chosen: list[str] = []
    for part in answer.replace(',', ' ').split():
        if not part.isdigit() or not 1 <= int(part) <= len(options):
            sys.stderr.write(f'not one of the choices: {part}\n')
            return []
        chosen.append(options[int(part) - 1])
    return chosen


def choose(
    options: list[str],
    *,
    prompt: str,
    missing: str,
    multi: bool = False,
) -> list[str]:
    """Return the chosen options, or nothing if the user declined.

    An empty result is a decline, never a default. Callers stop there:
    guessing on the user's behalf is exactly what the picker was for.
    """
    _require_tty(missing)
    if not options:
        return []
    if shutil.which('fzf') and not os.environ.get(NO_FZF):
        return _with_fzf(options, prompt=prompt, multi=multi)
    return _numbered(options, prompt=prompt, multi=multi)
