"""Tests for the hook that embeds a command's output in the README."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from git_a_grip import doc_block, embed_command

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


# Quoted so shlex keeps it in one argv slot, and run through this interpreter
# so the test needs nothing on PATH.
def _prints(code: str) -> str:
    return f'{sys.executable} -c "{code}"'


def _sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(doc_block, 'repo_root', lambda: tmp_path)
    monkeypatch.setattr(doc_block.restage, 'add', lambda _paths: 0)
    readme = tmp_path / 'README.md'
    readme.write_text('# proj\n\n<!-- help:start -->\n<!-- help:end -->\n')
    return readme


def test_output_lands_in_the_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readme = _sandbox(tmp_path, monkeypatch)

    code = embed_command.main([f'--command={_prints(r"print(chr(39))")}'])

    assert code == 0
    assert "```\n'\n```" in readme.read_text()


def test_a_second_run_changes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readme = _sandbox(tmp_path, monkeypatch)
    args = [f'--command={_prints("print(1)")}']

    embed_command.main(args)
    before = readme.read_text()
    embed_command.main(args)

    assert readme.read_text() == before


def test_a_failing_command_aborts_instead_of_embedding_its_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    readme = _sandbox(tmp_path, monkeypatch)

    code = embed_command.main(
        [f'--command={_prints("print(chr(98)); raise SystemExit(2)")}'],
    )

    assert code == 1
    # The README is untouched -- no half-output, no traceback in a fence.
    assert 'b' not in readme.read_text().split('start -->')[1]
    assert '--exit=2' in capsys.readouterr().err


def test_an_expected_non_zero_exit_is_allowed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readme = _sandbox(tmp_path, monkeypatch)

    code = embed_command.main(
        [
            f'--command={_prints("print(chr(98)); raise SystemExit(2)")}',
            '--exit=2',
        ],
    )

    assert code == 0
    assert '```\nb\n```' in readme.read_text()


def test_a_missing_command_is_reported_not_raised(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _sandbox(tmp_path, monkeypatch)

    assert embed_command.main(['--command=definitely-not-a-real-binary']) == 1
    assert 'cannot run' in capsys.readouterr().err


def test_no_command_at_all_explains_itself(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _sandbox(tmp_path, monkeypatch)

    assert embed_command.main([]) == 1
    assert '--command' in capsys.readouterr().err


def test_nothing_is_discovered_and_run_on_its_own(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The safety property, as a test: an executable sitting in the tree is
    # not a thing this hook runs. Only --command is.
    _sandbox(tmp_path, monkeypatch)
    script = tmp_path / 'bin' / 'evil.sh'
    script.parent.mkdir()
    script.write_text('#!/bin/sh\ntouch "$0.ran"\n')
    script.chmod(0o755)

    embed_command.main([f'--command={_prints("print(1)")}'])

    assert not (tmp_path / 'bin' / 'evil.sh.ran').exists()


def test_stderr_is_used_when_the_command_prints_usage_there(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readme = _sandbox(tmp_path, monkeypatch)
    code = r'import sys; sys.stderr.write(chr(117) + chr(10))'

    assert embed_command.main([f'--command={_prints(code)}']) == 0
    assert '```\nu\n```' in readme.read_text()


def test_trailing_whitespace_is_stripped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readme = _sandbox(tmp_path, monkeypatch)
    code = r'print(chr(97) + chr(32) + chr(32)); print(); print()'

    embed_command.main([f'--command={_prints(code)}'])

    assert '```\na\n```' in readme.read_text()


def test_unbalanced_quoting_is_an_error_not_a_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sandbox(tmp_path, monkeypatch)

    assert embed_command.main(['--command=echo "unclosed']) == 1
