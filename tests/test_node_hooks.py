"""Tests for the eslint and tsc hooks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from git_a_grip import node_hooks

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _record(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    workdirs: list[Path] | None = None,
) -> list[list[str]]:
    """Capture the commands the hook would run instead of running them."""
    calls: list[list[str]] = []

    def fake_run(command: list[str], workdir: Path, _tool: str) -> int:
        calls.append(command)
        if workdirs is not None:
            workdirs.append(workdir)
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


def test_dir_runs_the_tool_from_the_subdirectory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdirs: list[Path] = []
    _record(monkeypatch, tmp_path, workdirs)
    (tmp_path / 'web').mkdir()

    assert node_hooks.tsc(['--dir=web']) == 0
    assert workdirs == [tmp_path / 'web']


def test_dir_names_files_relative_to_the_subdirectory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pre-commit names files from the root; eslint runs from `web`."""
    calls = _record(monkeypatch, tmp_path)
    (tmp_path / 'web' / 'app').mkdir(parents=True)
    (tmp_path / 'web' / 'app' / 'page.tsx').write_text('const a = 1\n')
    monkeypatch.chdir(tmp_path)

    assert node_hooks.eslint(['--dir=web', 'web/app/page.tsx']) == 0
    assert 'app/page.tsx' in calls[0]
    assert 'web/app/page.tsx' not in calls[0]


def test_dir_drops_files_outside_the_subdirectory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A root-level file is covered by no config `web` is about to load."""
    calls = _record(monkeypatch, tmp_path)
    (tmp_path / 'web').mkdir()
    (tmp_path / 'scraper.ts').write_text('const a = 1\n')
    monkeypatch.chdir(tmp_path)

    assert node_hooks.eslint(['--dir=web', 'scraper.ts']) == 0
    assert calls == []


def test_dir_restages_by_the_path_pre_commit_gave(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """git add runs from the repo root, so the root-relative name is kept."""
    (tmp_path / 'web').mkdir()
    source = tmp_path / 'web' / 'a.ts'
    source.write_text('const a = 1\n')
    staged: list[list[str]] = []

    def fake_run(_command: list[str], _workdir: Path, _tool: str) -> int:
        source.write_text('const a = 1;\n')  # what --fix would do
        return 0

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(node_hooks, 'repo_root', lambda: tmp_path)
    monkeypatch.setattr(node_hooks, 'run', fake_run)
    monkeypatch.setattr(
        node_hooks.restage,
        'add',
        lambda paths: staged.append(paths) or 0,
    )

    assert node_hooks.eslint(['--dir=web', 'web/a.ts']) == 0
    assert staged == [['web/a.ts']]


def test_runner_falls_back_to_the_root_lockfile(tmp_path: Path) -> None:
    """A workspace keeps one lockfile at the top, above the linted package."""
    (tmp_path / 'pnpm-lock.yaml').touch()
    (tmp_path / 'web').mkdir()

    assert node_hooks.detect_runner(tmp_path / 'web', tmp_path) == 'pnpm exec'


def test_nearest_lockfile_wins_over_the_root(tmp_path: Path) -> None:
    """A subdirectory with its own lockfile is its own project."""
    (tmp_path / 'pnpm-lock.yaml').touch()
    (tmp_path / 'web').mkdir()
    (tmp_path / 'web' / 'package-lock.json').touch()

    runner = node_hooks.detect_runner(tmp_path / 'web', tmp_path)

    assert runner == 'npx --no-install'


def test_clean_env_drops_pre_commit_venv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('VIRTUAL_ENV', '/somewhere/hookenv')

    assert 'VIRTUAL_ENV' not in node_hooks.clean_env()
