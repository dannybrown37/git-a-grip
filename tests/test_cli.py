"""The `gag` dispatcher: the only entry point a person is expected to type."""

from __future__ import annotations

import pytest

from git_a_grip import cli

BAD_ARGS_CODE = 2
STUB_CODE = 7


def test_bare_gag_lists_every_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main([]) == 0

    out = capsys.readouterr().out
    for name in cli.COMMANDS:
        assert name in out


def test_help_and_bare_invocation_agree(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(['--help']) == 0
    first = capsys.readouterr().out
    assert cli.main(['help']) == 0

    assert capsys.readouterr().out == first


def test_version_prints_the_installed_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(['--version']) == 0

    assert cli.version.installed_version() in capsys.readouterr().out


def test_unknown_command_names_it_and_shows_usage(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(['bogus']) == BAD_ARGS_CODE

    err = capsys.readouterr().err
    assert 'bogus' in err
    assert 'usage: gag' in err


def test_the_rest_of_the_argv_reaches_the_subcommand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []
    monkeypatch.setitem(
        cli.COMMANDS,
        'audit',
        (lambda argv: seen.append(argv) or STUB_CODE, 'stub'),
    )

    assert cli.main(['audit', '--json', '~/projects']) == STUB_CODE
    assert seen == [['--json', '~/projects']]


@pytest.mark.parametrize('name', list(cli.COMMANDS))
def test_every_command_has_its_own_help(
    name: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The dispatcher must not swallow `--help`: each command prints its own.
    assert cli.main([name, '--help']) == 0

    assert f'gag {name}' in capsys.readouterr().out
