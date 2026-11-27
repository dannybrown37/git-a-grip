"""Tests for the cross-repo pre-commit audit."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from git_a_grip import audit

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

BAD_ARGS_CODE = 2

SELF_CONFIG = """\
repos:
  - repo: https://github.com/dannybrown37/git-a-grip
    rev: v0.3.1
    hooks:
      - id: commitizen-early
      - id: ruff-check
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.30.1
    hooks:
      - id: gitleaks
  - repo: local
    hooks:
      - id: tests
        entry: uv run pytest
"""

OTHER_CONFIG = """\
repos:
  - repo: https://github.com/dannybrown37/git-a-grip
    rev: v0.1.0
    hooks:
      - id: commitizen-early
"""


def _make_repo(root: Path, name: str, config: str | None) -> Path:
    repo = root / name
    (repo / '.git').mkdir(parents=True)
    if config is not None:
        (repo / audit.CONFIG_NAME).write_text(config)
    return repo


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / 'projects'
    _make_repo(root, 'alpha', SELF_CONFIG)
    _make_repo(root, 'beta', OTHER_CONFIG)
    _make_repo(root, 'gamma', None)
    (root / 'not-a-repo').mkdir()
    return root


def test_find_repos_skips_non_repos_and_nested_dirs(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / 'alpha' / '.venv' / 'src').mkdir(parents=True)
    (root / 'alpha' / 'sub').mkdir()

    names = [p.name for p in audit.find_repos([root])]

    assert names == ['alpha', 'beta', 'gamma']


def test_find_repos_skips_worktrees_of_a_clone(
    clone_with_worktree: tuple[Path, Path],
) -> None:
    clone, _ = clone_with_worktree

    assert audit.find_repos([clone.parent]) == [clone]


def test_report_groups_by_source(tmp_path: Path) -> None:
    audits = [audit.audit_repo(p) for p in audit.find_repos([_tree(tmp_path)])]

    report = audit.render(audits)

    assert '3 repos scanned, 2 with pre-commit hooks.' in report
    # Own hooks, with the rev each consumer pins.
    assert 'alpha                        v0.3.1' in report
    assert 'beta                         v0.1.0' in report
    # Third-party hooks are grouped under their source repo.
    assert 'https://github.com/gitleaks/gitleaks' in report
    # Local hooks keep their entry, and an unhooked repo is reported.
    assert 'uv run pytest' in report
    assert 'gamma' in report


def test_unpinned_rev_is_labelled(tmp_path: Path) -> None:
    root = tmp_path / 'projects'
    _make_repo(
        root,
        'alpha',
        'repos:\n  - repo: https://github.com/x/git-a-grip\n'
        '    hooks:\n      - id: ruff-check\n',
    )

    audits = [audit.audit_repo(p) for p in audit.find_repos([root])]
    report = audit.render(audits)

    assert 'unpinned' in report


def test_broken_config_is_reported_not_raised(tmp_path: Path) -> None:
    root = tmp_path / 'projects'
    _make_repo(root, 'alpha', 'repos: [oops\n')

    result = audit.audit_repo(root / 'alpha')

    assert result.error
    assert 'alpha' in audit.render([result])


def test_non_mapping_config_is_an_error(tmp_path: Path) -> None:
    root = tmp_path / 'projects'
    _make_repo(root, 'alpha', '- just a list\n')

    assert audit.audit_repo(root / 'alpha').error == 'config is not a mapping'


def test_json_output_classifies_each_hook(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _tree(tmp_path)

    code = audit.main([str(root), '--json'])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['version'] == audit.version.installed_version()
    repos = payload['repos']
    alpha = next(entry for entry in repos if entry['name'] == 'alpha')
    sources = {hook['id']: hook['source'] for hook in alpha['hooks']}
    assert sources == {
        'commitizen-early': 'self',
        'ruff-check': 'self',
        'gitleaks': 'third-party',
        'tests': 'local',
    }


def test_missing_directory_refuses(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = audit.main([str(tmp_path / 'nope')])

    assert code == BAD_ARGS_CODE
    assert 'not a directory' in capsys.readouterr().err


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert audit.main(['--help']) == 0
    assert 'gag audit' in capsys.readouterr().out


def test_report_leads_with_the_installed_version(tmp_path: Path) -> None:
    audits = [audit.audit_repo(p) for p in audit.find_repos([_tree(tmp_path)])]

    report = audit.render(audits)

    assert report.splitlines()[0].startswith('git-a-grip ')
    assert audit.version.installed_version() in report.splitlines()[0]


def test_stale_pins_are_flagged_against_the_installed_version() -> None:
    assert audit.rev_status('v0.1.0', '0.3.1') == 'behind'
    assert audit.rev_status('v0.3.1', '0.3.1') == 'current'
    assert audit.rev_status('v9.0.0', '0.3.1') == 'ahead'
    assert audit.rev_status('', '0.3.1') == ''


@pytest.mark.parametrize('checkout', [0, 1], ids=['clone', 'worktree'])
def test_default_roots_are_the_clones_siblings_even_from_a_worktree(
    clone_with_worktree: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    checkout: int,
) -> None:
    clone = clone_with_worktree[0]
    monkeypatch.chdir(clone_with_worktree[checkout])

    assert audit.default_roots() == [clone.parent]


@pytest.mark.parametrize(
    ('setup', 'rev', 'config_from'),
    [
        ([], 'v0.4.0', 'origin/HEAD'),
        ([('remote', 'set-head', 'origin', '-d')], 'v0.4.0', 'origin/main'),
        ([('remote', 'remove', 'origin')], 'v0.3.1', 'working tree'),
        (
            [
                ('rm', '--cached', '-q', audit.CONFIG_NAME),
                ('commit', '-m', 'drop config'),
                ('push', '-f', 'origin', 'HEAD:main'),
            ],
            'v0.3.1',
            'working tree',
        ),
        (
            [
                ('push', 'origin', 'HEAD:master'),
                ('rm', '--cached', '-q', audit.CONFIG_NAME),
                ('commit', '-m', 'drop config'),
                ('push', '-f', 'origin', 'HEAD:main'),
            ],
            'v0.3.1',
            'working tree',
        ),
    ],
    ids=[
        'origin-head',
        'no-origin-head',
        'no-remote',
        'not-on-origin',
        'stale-master-is-not-the-default',
    ],
)
def test_audit_reads_the_config_origin_has_not_the_stale_checkout(  # noqa: PLR0917 -- fixtures plus parametrize
    stale_clone: Path,
    git: Callable[..., None],
    capsys: pytest.CaptureFixture[str],
    setup: list[tuple[str, ...]],
    rev: str,
    config_from: str,
) -> None:
    for args in setup:
        git('-C', stale_clone, *args)

    assert audit.main([str(stale_clone.parent), '--json']) == 0

    (repo,) = json.loads(capsys.readouterr().out)['repos']
    assert [hook['rev'] for hook in repo['hooks']] == [rev]
    assert repo['config_from'] == config_from


def test_audit_repo_reads_the_working_tree_unless_asked(
    stale_clone: Path,
) -> None:
    assert audit.audit_repo(stale_clone).uses[0].rev == 'v0.3.1'
    assert audit.audit_repo(stale_clone, from_origin=True).uses[0].rev == (
        'v0.4.0'
    )


def test_audit_without_git_on_path_reads_the_working_tree(
    stale_clone: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('PATH', '')

    found = audit.audit_repo(stale_clone, from_origin=True)

    assert (found.uses[0].rev, found.config_from) == ('v0.3.1', 'working tree')
