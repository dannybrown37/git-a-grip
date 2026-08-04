"""Tests for the cross-repo rev sync."""

from __future__ import annotations

from typing import TYPE_CHECKING

from git_a_grip import audit, sync, version

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

BAD_ARGS_CODE = 2

CONFIG = """\
# A comment that must survive the rewrite.
repos:
  - repo: https://github.com/dannybrown37/git-a-grip
    rev: v0.1.0  # pinned deliberately
    hooks:
      - id: commitizen-early
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.30.1
    hooks:
      - id: gitleaks
"""


def _make_repo(root: Path, name: str, config: str | None) -> Path:
    repo = root / name
    (repo / '.git').mkdir(parents=True)
    if config is not None:
        (repo / audit.CONFIG_NAME).write_text(config)
    return repo


def test_rewrite_touches_only_the_matched_source() -> None:
    updated, old = sync.rewrite(CONFIG, version.REPO_URL, 'v0.4.0')

    assert old == 'v0.1.0'
    assert 'rev: v0.4.0  # pinned deliberately' in updated
    assert 'rev: v8.30.1' in updated
    assert updated.startswith('# A comment that must survive the rewrite.')


def test_rewrite_is_a_no_op_when_already_pinned() -> None:
    updated, old = sync.rewrite(CONFIG, version.REPO_URL, 'v0.1.0')

    assert old == ''
    assert updated == CONFIG


def test_rewrite_ignores_an_absent_source() -> None:
    _, old = sync.rewrite(CONFIG, 'https://github.com/someone/else', 'v1.0.0')

    assert old == ''


def test_url_spellings_of_one_repo_match() -> None:
    assert sync.matches_source(
        'git@github.com:dannybrown37/git-a-grip.git',
        version.REPO_URL,
    )
    assert not sync.matches_source(
        'https://github.com/other/git-a-grip',
        version.REPO_URL,
    )


def test_plan_finds_stale_repos_without_writing(tmp_path: Path) -> None:
    root = tmp_path / 'projects'
    _make_repo(root, 'alpha', CONFIG)
    _make_repo(root, 'beta', CONFIG.replace('v0.1.0', 'v0.4.0'))
    _make_repo(root, 'gamma', None)

    changes = sync.plan([root], version.REPO_URL, 'v0.4.0')

    assert [c.name for c in changes] == ['alpha']
    assert (root / 'alpha' / audit.CONFIG_NAME).read_text() == CONFIG


def test_apply_writes_the_planned_changes(tmp_path: Path) -> None:
    root = tmp_path / 'projects'
    _make_repo(root, 'alpha', CONFIG)

    written = sync.apply(sync.plan([root], version.REPO_URL, 'v0.4.0'))

    assert len(written) == 1
    text = (root / 'alpha' / audit.CONFIG_NAME).read_text()
    assert 'rev: v0.4.0' in text
    assert 'v0.1.0' not in text


def test_main_dry_run_reports_and_leaves_files_alone(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / 'projects'
    _make_repo(root, 'alpha', CONFIG)

    code = sync.main([str(root), '--to', 'v0.4.0'])

    out = capsys.readouterr().out
    assert code == 0
    assert 'Would pin' in out
    assert 'alpha' in out
    assert 'Re-run with --write' in out
    assert (root / 'alpha' / audit.CONFIG_NAME).read_text() == CONFIG


def test_main_write_applies(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / 'projects'
    _make_repo(root, 'alpha', CONFIG)

    code = sync.main([str(root), '--to=0.4.0', '--write'])

    assert code == 0
    assert 'Pinned' in capsys.readouterr().out
    assert 'rev: v0.4.0' in (root / 'alpha' / audit.CONFIG_NAME).read_text()


def test_main_reports_nothing_to_do(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / 'projects'
    _make_repo(root, 'alpha', CONFIG)

    sync.main([str(root), '--to', 'v0.1.0'])

    assert 'already at v0.1.0' in capsys.readouterr().out


def test_main_can_target_another_source(tmp_path: Path) -> None:
    root = tmp_path / 'projects'
    _make_repo(root, 'alpha', CONFIG)

    sync.main(
        [
            str(root),
            '--repo',
            'https://github.com/gitleaks/gitleaks',
            '--to',
            'v8.31.0',
            '--write',
        ],
    )

    text = (root / 'alpha' / audit.CONFIG_NAME).read_text()
    assert 'rev: v8.31.0' in text
    assert 'rev: v0.1.0' in text


def test_missing_directory_refuses(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = sync.main([str(tmp_path / 'nope'), '--to', 'v1.0.0'])

    assert code == BAD_ARGS_CODE
    assert 'not a directory' in capsys.readouterr().err


def test_staleness_note_fires_when_the_install_is_behind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sync, 'latest_tag', lambda _: 'v0.8.0')

    note = sync.staleness_note(version.REPO_URL, 'v0.7.0')

    assert 'v0.7.0' in note
    assert 'v0.8.0' in note
    assert '--latest' in note


def test_staleness_note_is_silent_when_current_or_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sync, 'latest_tag', lambda _: 'v0.8.0')
    assert sync.staleness_note(version.REPO_URL, 'v0.8.0') == ''
    assert sync.staleness_note(version.REPO_URL, 'v0.9.0') == ''

    monkeypatch.setattr(sync, 'latest_tag', lambda _: '')
    assert sync.staleness_note(version.REPO_URL, 'v0.7.0') == ''


def test_an_explicit_target_asks_the_remote_nothing() -> None:
    assert not sync.targets_installed(['--to', 'v0.4.0'])
    assert not sync.targets_installed(['--to=v0.4.0'])
    assert not sync.targets_installed(['--latest'])
    assert sync.targets_installed(['--write'])


def test_main_warns_but_still_reports_when_behind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / 'projects'
    _make_repo(root, 'alpha', CONFIG)
    monkeypatch.setattr(sync, 'latest_tag', lambda _: 'v99.0.0')

    code = sync.main([str(root)])

    captured = capsys.readouterr()
    assert code == 0
    assert 'v99.0.0 is the newest tag' in captured.err
    assert 'alpha' in captured.out


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert sync.main(['--help']) == 0
    assert 'gag sync' in capsys.readouterr().out
