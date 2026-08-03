"""Tests for the eslint and tsc hooks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from git_a_grip import node_hooks

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _record(monkeypatch: pytest.MonkeyPatch, root: Path) -> list[list[str]]:
    """Capture the commands the hook would run instead of running them."""
    calls: list[list[str]] = []

    def fake_run(command: list[str], _root: Path, _tool: str) -> int:
        calls.append(command)
        return 0

    monkeypatch.setattr(node_hooks, 'repo_root', lambda: root)
    monkeypatch.setattr(node_hooks, 'run', fake_run)
    monkeypatch.setattr(node_hooks.restage, 'add', lambda _paths: 0)
    return calls


def test_runner_follows_the_lockfile(tmp_path: Path) -> None:
    (tmp_path / 'pnpm-lock.yaml').touch()

    assert node_hooks.detect_runner(tmp_path) == 'pnpm exec'


def test_runner_defaults_to_npx(tmp_path: Path) -> None:
    assert node_hooks.detect_runner(tmp_path) == node_hooks.DEFAULT_RUNNER


def test_explicit_runner_wins(tmp_path: Path) -> None:
    (tmp_path / 'pnpm-lock.yaml').touch()

    runner, rest = node_hooks.split_args(
        ['--runner=yarn', 'a.ts'],
        tmp_path,
    )

    assert runner == ['yarn']
    assert rest == ['a.ts']


def test_eslint_fixes_and_fails_on_warnings_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _record(monkeypatch, tmp_path)
    source = tmp_path / 'a.ts'
    source.write_text('const a = 1\n')

    assert node_hooks.eslint([str(source)]) == 0
    assert calls[0][:4] == ['npx', '--no-install', 'eslint', '--fix']
    assert '--max-warnings=0' in calls[0]


def test_eslint_respects_an_explicit_max_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _record(monkeypatch, tmp_path)
    source = tmp_path / 'a.ts'
    source.write_text('const a = 1\n')

    node_hooks.eslint(['--max-warnings=5', str(source)])

    assert '--max-warnings=0' not in calls[0]
    assert '--max-warnings=5' in calls[0]


def test_eslint_restages_what_it_rewrote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / 'a.ts'
    source.write_text('const a = 1\n')
    staged: list[list[str]] = []

    def fake_run(_command: list[str], _root: Path, _tool: str) -> int:
        source.write_text('const a = 1;\n')  # what --fix would do
        return 0

    monkeypatch.setattr(node_hooks, 'repo_root', lambda: tmp_path)
    monkeypatch.setattr(node_hooks, 'run', fake_run)
    monkeypatch.setattr(
        node_hooks.restage,
        'add',
        lambda paths: staged.append(paths) or 0,
    )

    assert node_hooks.eslint([str(source)]) == 0
    assert staged == [[str(source)]]


def test_eslint_does_nothing_without_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _record(monkeypatch, tmp_path)

    assert node_hooks.eslint([]) == 0
    assert calls == []


def test_tsc_never_passes_filenames_and_names_the_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _record(monkeypatch, tmp_path)

    assert node_hooks.tsc([]) == 0
    assert calls[0] == ['npx', '--no-install', 'tsc', '--noEmit', '-p', '.']


def test_tsc_keeps_an_explicit_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _record(monkeypatch, tmp_path)

    node_hooks.tsc(['-p', 'tsconfig.build.json'])

    assert calls[0].count('-p') == 1
    assert calls[0][-1] == 'tsconfig.build.json'


def test_clean_env_drops_pre_commit_venv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('VIRTUAL_ENV', '/somewhere/hookenv')

    assert 'VIRTUAL_ENV' not in node_hooks.clean_env()
