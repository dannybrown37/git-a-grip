"""The hook dispatcher: what pre-commit reaches through `python -m`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from git_a_grip import hooks

if TYPE_CHECKING:
    import pytest

BAD_ARGS_CODE = 2
STUB_CODE = 7


def test_no_hook_named_points_at_the_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert hooks.main([]) == BAD_ARGS_CODE

    assert 'gag --help' in capsys.readouterr().err


def test_unknown_hook_lists_the_known_ones(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert hooks.main(['nope']) == BAD_ARGS_CODE

    err = capsys.readouterr().err
    assert 'nope' in err
    for name in hooks.HOOKS:
        assert name in err


def test_the_rest_of_the_argv_reaches_the_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []
    monkeypatch.setitem(
        hooks.HOOKS,
        'pytest',
        lambda argv: seen.append(argv) or STUB_CODE,
    )

    assert hooks.main(['pytest', 'tests/', '-q']) == STUB_CODE
    assert seen == [['tests/', '-q']]


def test_ruff_check_always_gets_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    # `--fix` is the whole point of the hook -- it is what makes it re-stage
    # rather than merely complain, so it cannot come from the consumer's args.
    seen: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        hooks.ruff_hooks,
        'run',
        lambda sub, argv: seen.append((sub, argv)) or 0,
    )

    assert hooks.main(['ruff-check', 'a.py']) == 0
    assert seen == [('check', ['--fix', 'a.py'])]


def test_commitizen_early_ignores_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # It recovers the message from git's argv, not from pre-commit's.
    monkeypatch.setattr(hooks.commitizen_early, 'main', lambda: STUB_CODE)

    assert hooks.main(['commitizen-early', 'whatever']) == STUB_CODE
