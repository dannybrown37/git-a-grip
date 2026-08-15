"""Tests for the type-checking hook."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from git_a_grip import mypy_hook

if TYPE_CHECKING:
    import pytest

TYPE_ERROR_EXIT = 1


def _calls(
    monkeypatch: pytest.MonkeyPatch,
    code: int,
) -> list[dict[str, object]]:
    """Capture what the hook would run, and hand back a chosen exit code."""
    calls: list[dict[str, object]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> object:
        calls.append({'cmd': cmd, **kwargs})
        return subprocess.CompletedProcess(args=cmd, returncode=code)

    monkeypatch.setattr(mypy_hook, 'repo_root', lambda: '/repo')
    monkeypatch.setattr(mypy_hook.subprocess, 'run', fake_run)
    return calls


def test_it_names_no_targets_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The contract of the hook: what gets checked comes from the project's
    # mypy config, so the hook and a person's own `mypy` cannot disagree.
    # A default target here -- even `.` -- would break exactly that.
    calls = _calls(monkeypatch, 0)

    assert mypy_hook.main([]) == 0
    assert calls[0]['cmd'] == ['uv', 'run', '--with', 'mypy', 'mypy']


def test_the_default_runner_installs_the_checker_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The point of `--with`: `- id: mypy` and nothing else is the whole
    # configuration. A bare `uv run mypy` resolves the project's env but
    # then demands the project declare a checker it never imports -- the
    # dependency group this hook exists in order not to need.
    calls = _calls(monkeypatch, 0)

    mypy_hook.main([])

    assert '--with' in calls[0]['cmd']


def test_runner_flag_replaces_the_command_outright(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Not a prefix: naming an environment and naming the checker that runs
    # in it is one decision, which is what lets pyright or ty stand in.
    calls = _calls(monkeypatch, 0)

    assert mypy_hook.main(['--runner=uv run ty check']) == 0
    assert calls[0]['cmd'] == ['uv', 'run', 'ty', 'check']


def test_args_reach_the_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _calls(monkeypatch, 0)

    assert mypy_hook.main(['--strict', 'src']) == 0
    assert calls[0]['cmd'] == [
        'uv',
        'run',
        '--with',
        'mypy',
        'mypy',
        '--strict',
        'src',
    ]


def test_runs_from_the_repo_root_and_returns_the_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _calls(monkeypatch, TYPE_ERROR_EXIT)

    assert mypy_hook.main([]) == TYPE_ERROR_EXIT
    assert calls[0]['cwd'] == '/repo'


def test_empty_runner_fails_rather_than_running_nothing() -> None:
    assert mypy_hook.main(['--runner=']) == 1


def test_missing_runner_binary_reports_which_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(mypy_hook, 'repo_root', lambda: '/repo')
    monkeypatch.setattr(mypy_hook.subprocess, 'run', explode)

    assert mypy_hook.main([]) == 1
    assert "'uv'" in capsys.readouterr().err


def test_a_usage_exit_says_where_targets_are_meant_to_come_from(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # mypy's own message for this is `usage: mypy [-h] ...`, which does not
    # tell a person that the answer belongs in their config rather than in
    # the hook's args.
    _calls(monkeypatch, mypy_hook.USAGE_EXIT)

    assert mypy_hook.main([]) == mypy_hook.USAGE_EXIT

    err = capsys.readouterr().err
    assert 'files = ' in err


def test_the_usage_hint_does_not_claim_mypy_is_the_one_complaining(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # `uv run --group typing mypy` against an undeclared group exits 2
    # before mypy starts. The hook cannot tell that apart from mypy's own
    # usage exit, so the hint has to name both -- it once asserted mypy had
    # nothing to check and sent a person to edit the wrong config file.
    _calls(monkeypatch, mypy_hook.USAGE_EXIT)

    mypy_hook.main([])

    assert 'runner' in capsys.readouterr().err


def test_a_usage_exit_with_a_target_named_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Exit 2 with targets already named is some other usage error, and the
    # hint would be a confident guess at the wrong one.
    _calls(monkeypatch, mypy_hook.USAGE_EXIT)

    assert mypy_hook.main(['src']) == mypy_hook.USAGE_EXIT
    assert capsys.readouterr().err == ''


def test_type_errors_pass_through_unexplained(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # mypy has already said what is wrong, on stdout, in its own words.
    _calls(monkeypatch, TYPE_ERROR_EXIT)

    assert mypy_hook.main([]) == TYPE_ERROR_EXIT
    assert capsys.readouterr().err == ''


def test_what_counts_as_naming_a_target() -> None:
    assert mypy_hook.names_a_target(['src'])
    assert mypy_hook.names_a_target(['-p', 'mypkg'])
    assert mypy_hook.names_a_target(['--package=mypkg'])
    assert mypy_hook.names_a_target(['-c', 'print(1)'])
    assert not mypy_hook.names_a_target([])
    assert not mypy_hook.names_a_target(['--strict'])
