"""Tests for the hook that runs a generator and re-stages what it wrote."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from git_a_grip import doc_block, regen_file

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


# Quoted so shlex keeps it in one argv slot, and run through this interpreter
# so the test needs nothing on PATH.
def _script(code: str) -> str:
    return f'{sys.executable} -c "{code}"'


def _writes(path: str, text: str) -> str:
    code = (
        f'open({chr(39)}{path}{chr(39)}, {chr(39)}w{chr(39)})'
        f'.write({chr(39)}{text}{chr(39)})'
    )
    return _script(code)


def _sandbox(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> list[list[str]]:
    """Point the hook at tmp_path and record what it would `git add`."""
    added: list[list[str]] = []
    monkeypatch.setattr(doc_block, 'repo_root', lambda: tmp_path)
    monkeypatch.setattr(
        regen_file.restage,
        'add',
        lambda paths: added.append(paths) or 0,
    )
    return added


def test_a_rewritten_file_is_restaged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    added = _sandbox(tmp_path, monkeypatch)
    (tmp_path / 'README.md').write_text('stale\n')

    code = regen_file.main(
        [f'--command={_writes("README.md", "fresh")}', '--file=README.md'],
    )

    assert code == 0
    assert (tmp_path / 'README.md').read_text() == 'fresh'
    assert added == [[str(tmp_path / 'README.md')]]


def test_an_unchanged_file_is_not_restaged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The generator ran and decided nothing had moved. Touching the index
    # anyway would make every commit carry a file nobody edited.
    added = _sandbox(tmp_path, monkeypatch)
    (tmp_path / 'README.md').write_text('same')

    code = regen_file.main(
        [f'--command={_writes("README.md", "same")}', '--file=README.md'],
    )

    assert code == 0
    assert added == []


def test_several_files_are_named_and_only_the_changed_one_restaged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    added = _sandbox(tmp_path, monkeypatch)
    (tmp_path / 'a.md').write_text('old')
    (tmp_path / 'b.md').write_text('steady')

    code = regen_file.main(
        [
            f'--command={_writes("a.md", "new")}',
            '--file=a.md',
            '--file=b.md',
        ],
    )

    assert code == 0
    assert added == [[str(tmp_path / 'a.md')]]


def test_the_command_runs_from_the_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A relative path in the generator resolves against the root, not against
    # whatever directory the committing shell happened to be in.
    _sandbox(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path.parent)
    (tmp_path / 'docs').mkdir()

    code = regen_file.main(
        [
            f'--command={_writes("docs/out.md", "here")}',
            '--file=docs/out.md',
        ],
    )

    assert code == 0
    assert (tmp_path / 'docs' / 'out.md').read_text() == 'here'


def test_a_failing_command_aborts_the_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    added = _sandbox(tmp_path, monkeypatch)
    (tmp_path / 'README.md').write_text('stale\n')

    code = regen_file.main(
        [
            f'--command={_script("raise SystemExit(2)")}',
            '--file=README.md',
        ],
    )

    assert code == 1
    # Half-written output is not staged on the way out.
    assert added == []
    assert 'exited 2' in capsys.readouterr().err


def test_a_named_file_the_command_never_wrote_is_an_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Silence here means a renamed output path goes unnoticed for months,
    # which is the drift this package exists to stop.
    _sandbox(tmp_path, monkeypatch)

    code = regen_file.main(
        [f'--command={_script("pass")}', '--file=missing.md'],
    )

    assert code == 1
    assert 'missing.md' in capsys.readouterr().err


def test_no_command_at_all_explains_itself(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _sandbox(tmp_path, monkeypatch)

    assert regen_file.main(['--file=README.md']) == 1
    assert '--command' in capsys.readouterr().err


def test_no_file_at_all_explains_itself(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _sandbox(tmp_path, monkeypatch)

    assert regen_file.main([f'--command={_script("pass")}']) == 1
    assert '--file' in capsys.readouterr().err


def test_a_missing_binary_is_reported_not_raised(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _sandbox(tmp_path, monkeypatch)

    code = regen_file.main(
        ['--command=definitely-not-a-real-binary', '--file=README.md'],
    )

    assert code == 1
    assert 'cannot run' in capsys.readouterr().err


def test_unbalanced_quoting_is_an_error_not_a_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sandbox(tmp_path, monkeypatch)

    assert regen_file.main(['--command=echo "unclosed', '--file=x']) == 1


def test_nothing_is_discovered_and_run_on_its_own(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The same safety property embed-command holds: an executable sitting in
    # the tree is not a thing this hook runs. Only --command is.
    _sandbox(tmp_path, monkeypatch)
    script = tmp_path / 'bin' / 'evil.sh'
    script.parent.mkdir()
    script.write_text('#!/bin/sh\ntouch "$0.ran"\n')
    script.chmod(0o755)
    (tmp_path / 'README.md').write_text('x')

    regen_file.main([f'--command={_script("pass")}', '--file=README.md'])

    assert not (tmp_path / 'bin' / 'evil.sh.ran').exists()


def test_the_command_is_not_run_through_a_shell(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `&&` is an argument to echo, not a second command. A config that wants
    # two steps writes two hook entries.
    _sandbox(tmp_path, monkeypatch)
    (tmp_path / 'README.md').write_text('x')

    regen_file.main(
        [
            '--command=echo a && touch pwned',
            '--file=README.md',
        ],
    )

    assert not (tmp_path / 'pwned').exists()
