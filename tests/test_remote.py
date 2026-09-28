"""Tests for the at-a-glance GitHub status of every local repo."""

from __future__ import annotations

import io
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest

from git_a_grip import remote

from pathlib import Path

if TYPE_CHECKING:
    from collections.abc import Callable

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
BAD_ARGS_CODE = 2
OPEN_PRS = 2
OPEN_ISSUES_EXCLUDING_PRS = 3


@pytest.mark.parametrize(
    ('url', 'expected'),
    [
        ('git@github.com:me/proj.git', ('me', 'proj')),
        ('https://github.com/me/proj.git', ('me', 'proj')),
        ('https://github.com/me/proj', ('me', 'proj')),
        ('https://github.com/me/proj/', ('me', 'proj')),
        ('ssh://git@github.com/me/my.proj.git', ('me', 'my.proj')),
        ('https://gitlab.com/me/proj.git', None),
        ('', None),
        # Anything outside GitHub's name alphabet never reaches `gh api`.
        ('https://github.com/me/pr;oj', None),
        ('https://github.com/../proj', None),
    ],
)
def test_parse_github_slug(url: str, expected: tuple[str, str] | None) -> None:
    assert remote.parse_github_slug(url) == expected


@pytest.mark.parametrize(
    ('stamp', 'expected'),
    [
        ('2026-09-27T11:59:30Z', 'just now'),
        ('2026-09-27T11:15:00Z', '45m ago'),
        ('2026-09-27T07:00:00Z', '5h ago'),
        ('2026-09-24T12:00:00Z', '3d ago'),
        ('2025-09-27T12:00:00Z', '365d ago'),
        ('', '-'),
    ],
)
def test_age(stamp: str, expected: str) -> None:
    assert remote.age(stamp, NOW) == expected


def _run(workflow: int, status: str, conclusion: str | None, at: str) -> dict:
    return {
        'workflow_id': workflow,
        'name': f'wf{workflow}',
        'status': status,
        'conclusion': conclusion,
        'updated_at': at,
    }


@pytest.mark.parametrize(
    ('runs', 'expected'),
    [
        ([], ('none', '')),
        (
            [_run(1, 'completed', 'success', '2026-09-27T10:00:00Z')],
            ('success', '2026-09-27T10:00:00Z'),
        ),
        # Only each workflow's newest run counts: an old failure that was
        # since fixed is not a red build.
        (
            [
                _run(1, 'completed', 'success', '2026-09-27T10:00:00Z'),
                _run(1, 'completed', 'failure', '2026-09-26T10:00:00Z'),
            ],
            ('success', '2026-09-27T10:00:00Z'),
        ),
        # But a green release workflow does not hide a red ci workflow.
        (
            [
                _run(2, 'completed', 'success', '2026-09-27T10:00:00Z'),
                _run(1, 'completed', 'failure', '2026-09-26T10:00:00Z'),
            ],
            ('failure', '2026-09-27T10:00:00Z'),
        ),
        (
            [
                _run(1, 'in_progress', None, '2026-09-27T10:00:00Z'),
                _run(2, 'completed', 'success', '2026-09-26T10:00:00Z'),
            ],
            ('running', '2026-09-27T10:00:00Z'),
        ),
        (
            [_run(1, 'completed', 'cancelled', '2026-09-27T10:00:00Z')],
            ('cancelled', '2026-09-27T10:00:00Z'),
        ),
    ],
)
def test_ci_status(runs: list[dict], expected: tuple[str, str]) -> None:
    assert remote.ci_status(runs) == expected


REPO_PAYLOAD = {
    'default_branch': 'main',
    'visibility': 'public',
    'archived': False,
    'pushed_at': '2026-09-26T12:00:00Z',
    'open_issues_count': 5,
    'security_and_analysis': {
        'secret_scanning': {'status': 'enabled'},
        'secret_scanning_push_protection': {'status': 'enabled'},
        'dependabot_security_updates': {'status': 'disabled'},
    },
}


def _fake_gh(responses: dict[str, tuple[int, Any]]) -> remote.Gh:
    def gh(path: str) -> tuple[int, Any]:
        for prefix, response in responses.items():
            if path.startswith(prefix):
                return response
        return 404, {}

    return gh


def _responses(**overrides: tuple[int, Any]) -> dict[str, tuple[int, Any]]:
    base = {
        'repos/me/proj/branches/main/protection': (404, {}),
        'repos/me/proj/rules/branches/main': (200, []),
        'repos/me/proj/actions/runs': (
            200,
            {
                'workflow_runs': [
                    _run(1, 'completed', 'success', '2026-09-27T10:00:00Z'),
                ],
            },
        ),
        'repos/me/proj/pulls': (200, [{}, {}]),
        'repos/me/proj': (200, REPO_PAYLOAD),
    }
    return base | overrides


def test_fetch_status_reads_everything_off_one_repo() -> None:
    status = remote.fetch_status('me', 'proj', _fake_gh(_responses()))

    assert status.branch == 'main'
    assert status.protection == 'none'
    assert status.ci == 'success'
    assert status.last_run == '2026-09-27T10:00:00Z'
    assert status.pushed_at == '2026-09-26T12:00:00Z'
    assert status.open_prs == OPEN_PRS
    # GitHub counts PRs as issues; the column should not.
    assert status.open_issues == OPEN_ISSUES_EXCLUDING_PRS
    assert status.security == ['secret-scanning', 'push-protection']


@pytest.mark.parametrize(
    ('overrides', 'expected'),
    [
        (
            {'repos/me/proj/branches/main/protection': (200, {})},
            'classic',
        ),
        (
            {
                'repos/me/proj/rules/branches/main': (
                    200,
                    [{'type': 'pull_request'}, {'type': 'deletion'}],
                ),
            },
            'ruleset',
        ),
        (
            {
                'repos/me/proj/branches/main/protection': (200, {}),
                'repos/me/proj/rules/branches/main': (
                    200,
                    [{'type': 'deletion'}],
                ),
            },
            'classic+ruleset',
        ),
        # Private repos on a free plan: GitHub refuses to say.
        (
            {
                'repos/me/proj/branches/main/protection': (403, {}),
                'repos/me/proj/rules/branches/main': (403, {}),
            },
            'unknown',
        ),
    ],
)
def test_protection_sources(
    overrides: dict[str, tuple[int, Any]],
    expected: str,
) -> None:
    gh = _fake_gh(_responses(**overrides))

    status = remote.fetch_status('me', 'proj', gh)

    assert status.protection == expected


def test_fetch_status_reports_an_unreachable_repo() -> None:
    status = remote.fetch_status(
        'me',
        'proj',
        _fake_gh({'repos/me/proj': (404, {'message': 'Not Found'})}),
    )

    assert status.error == 'Not Found'


def test_render_flags_what_needs_attention() -> None:
    rows = [
        remote.RepoRemote(
            name='alpha',
            slug='me/alpha',
            status=remote.RemoteStatus(
                branch='main',
                protection='none',
                ci='failure',
                last_run='2026-09-27T10:00:00Z',
                pushed_at='2026-09-26T12:00:00Z',
                open_prs=1,
                open_issues=0,
            ),
        ),
        remote.RepoRemote(name='beta', slug='', note='no GitHub remote'),
    ]

    report = remote.render(rows, NOW)

    alpha = next(line for line in report.splitlines() if 'alpha' in line)
    assert 'none' in alpha
    assert 'failure' in alpha
    assert '2h ago' in alpha
    assert '1d ago' in alpha
    assert 'beta' in report
    assert 'no GitHub remote' in report
    assert '1 unprotected' in report
    assert '1 failing' in report


def test_json_carries_raw_timestamps() -> None:
    rows = [
        remote.RepoRemote(
            name='alpha',
            slug='me/alpha',
            status=remote.RemoteStatus(branch='main', last_run='2026-01-01'),
        ),
    ]

    payload = json.loads(remote.as_json(rows))

    assert payload['repos'][0]['slug'] == 'me/alpha'
    assert payload['repos'][0]['status']['last_run'] == '2026-01-01'


def test_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert remote.main(['--help']) == 0

    assert 'gag remote' in capsys.readouterr().out


def test_missing_directory_is_a_usage_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert remote.main([str(tmp_path / 'nope')]) == BAD_ARGS_CODE

    assert 'not a directory' in capsys.readouterr().err


def test_missing_gh_says_how_to_fix_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(remote.shutil, 'which', lambda _: None)

    assert remote.main([str(tmp_path)]) == BAD_ARGS_CODE

    assert 'gh' in capsys.readouterr().err


def _row_line(report: str, name: str) -> str:
    return next(line for line in report.splitlines() if name in line)


def _quiet_row(**fields: Any) -> remote.RepoRemote:  # noqa: ANN401
    base: dict[str, Any] = {
        'branch': 'main',
        'protection': 'unknown',
        'ci': 'none',
        'open_prs': 0,
        'open_issues': None,
    }
    return remote.RepoRemote(
        name='quiet',
        slug='me/quiet',
        status=remote.RemoteStatus(**(base | fields)),
    )


@pytest.mark.parametrize('noise', ['unknown', '?', ' 0 ', ' none '])
def test_empty_values_render_blank(noise: str) -> None:
    line = _row_line(remote.render([_quiet_row()], NOW), 'quiet')

    assert noise not in line


def test_unprotected_is_still_spelled_out() -> None:
    line = _row_line(
        remote.render([_quiet_row(protection='none')], NOW),
        'quiet',
    )

    assert ' none ' in line


@pytest.mark.parametrize(
    ('fields', 'text', 'colour'),
    [
        ({'protection': 'none'}, 'none', remote.RED),
        ({'protection': 'ruleset'}, 'ruleset', remote.GREEN),
        ({'ci': 'failure'}, 'failure', remote.RED),
        ({'ci': 'running'}, 'running', remote.YELLOW),
        ({'ci': 'success'}, 'success', remote.GREEN),
    ],
)
def test_colour_marks_what_matters(
    fields: dict[str, str],
    text: str,
    colour: str,
) -> None:
    report = remote.render([_quiet_row(**fields)], NOW, colour=True)

    assert f'{colour}{text}' in report


def test_colour_keeps_columns_aligned() -> None:
    rows = [
        _quiet_row(protection='none', ci='failure'),
        _quiet_row(protection='ruleset', ci='success'),
    ]
    plain = remote.render(rows, NOW).splitlines()
    coloured = remote.render(rows, NOW, colour=True).splitlines()

    assert [remote.strip_ansi(line) for line in coloured] == plain


def test_plain_render_has_no_escape_codes() -> None:
    report = remote.render([_quiet_row(ci='failure')], NOW)

    assert '\x1b' not in report


@pytest.mark.parametrize(
    ('tty', 'no_colour', 'expected'),
    [(True, None, True), (False, None, False), (True, '1', False)],
)
def test_use_colour(
    monkeypatch: pytest.MonkeyPatch,
    tty: bool,  # noqa: FBT001
    no_colour: str | None,
    expected: bool,  # noqa: FBT001
) -> None:
    monkeypatch.delenv('NO_COLOR', raising=False)
    if no_colour is not None:
        monkeypatch.setenv('NO_COLOR', no_colour)
    stream = io.StringIO()
    monkeypatch.setattr(stream, 'isatty', lambda: tty)

    assert remote.use_colour(stream) is expected


def _commit_at(repo: Path, when: datetime) -> None:
    stamp = when.isoformat()
    env = os.environ | {
        'GIT_AUTHOR_DATE': stamp,
        'GIT_COMMITTER_DATE': stamp,
        'GIT_AUTHOR_NAME': 't',
        'GIT_AUTHOR_EMAIL': 't@example.com',
        'GIT_COMMITTER_NAME': 't',
        'GIT_COMMITTER_EMAIL': 't@example.com',
    }
    run: Callable[..., Any] = subprocess.run
    run(['git', 'init', '-q', str(repo)], check=True)
    run(
        ['git', '-C', str(repo), 'commit', '-q', '--allow-empty', '-m', 'x'],
        check=True,
        env=env,
    )


def test_last_touched_reads_the_newest_commit(tmp_path: Path) -> None:
    when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    _commit_at(tmp_path / 'r', when)

    assert remote.last_touched(tmp_path / 'r') == when


def test_last_touched_of_an_empty_repo_is_none(tmp_path: Path) -> None:
    run: Callable[..., Any] = subprocess.run
    run(['git', 'init', '-q', str(tmp_path)], check=True)

    assert remote.last_touched(tmp_path) is None


def test_select_recent_drops_stale_and_empty_repos() -> None:
    touched = {
        Path('fresh'): NOW - timedelta(days=10),
        Path('edge'): NOW - timedelta(days=remote.RECENT_DAYS - 1),
        Path('stale'): NOW - timedelta(days=remote.RECENT_DAYS + 1),
        Path('empty'): None,
    }

    kept = remote.select_recent(list(touched), NOW, touched.get)

    assert kept == [Path('fresh'), Path('edge')]


def test_hidden_repos_are_counted_in_the_report() -> None:
    report = remote.render([_quiet_row()], NOW, hidden=4)

    assert '4 repos untouched in 90 days hidden' in report
    assert '--all-repos' in report


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_progress_ticks_on_a_tty_and_clears_itself() -> None:
    stream = _Tty()

    with remote.Progress(3, stream) as progress:
        progress.tick()
        progress.tick()

    out = stream.getvalue()
    assert '2/3' in out
    assert out.endswith('\r\x1b[K')


def test_progress_is_silent_off_a_tty() -> None:
    stream = io.StringIO()

    with remote.Progress(3, stream) as progress:
        progress.tick()

    assert stream.getvalue() == ''


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('old-thing\ndotfiles\n', {'old-thing', 'dotfiles'}),
        ('# retired\n\n  spaced  \n', {'spaced'}),
        ('', set()),
    ],
)
def test_read_skips(tmp_path: Path, text: str, expected: set[str]) -> None:
    path = tmp_path / 'remote-skip'
    path.write_text(text)

    assert remote.read_skips(path) == expected


def test_a_missing_skip_file_skips_nothing(tmp_path: Path) -> None:
    assert remote.read_skips(tmp_path / 'absent') == set()


def test_skip_path_follows_xdg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))

    assert remote.skip_path() == tmp_path / 'git-a-grip' / 'remote-skip'


def test_skipped_repos_are_counted_in_the_report() -> None:
    report = remote.render([_quiet_row()], NOW, skipped=2)

    assert '2 repos skipped by' in report
    assert 'remote-skip' in report


def test_main_never_asks_github_about_a_skipped_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = tmp_path / 'config'
    (config / 'git-a-grip').mkdir(parents=True)
    (config / 'git-a-grip' / 'remote-skip').write_text('ignored\n')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(config))
    monkeypatch.setattr(remote.shutil, 'which', lambda _: '/usr/bin/gh')
    repos = [tmp_path / 'kept', tmp_path / 'ignored']
    monkeypatch.setattr(remote.audit, 'find_repos', lambda _: repos)
    inspected: list[str] = []

    def fake_inspect(path: Path) -> remote.RepoRemote:
        inspected.append(path.name)
        return remote.RepoRemote(name=path.name, slug='', note='n/a')

    monkeypatch.setattr(remote, 'inspect', fake_inspect)

    assert remote.main(['--all-repos', str(tmp_path)]) == 0
    assert inspected == ['kept']
    assert '1 repos skipped by' in capsys.readouterr().out


def _hooked_repo(tmp_path: Path, config: str, *installed: str) -> Path:
    repo = tmp_path / 'repo'
    run: Callable[..., Any] = subprocess.run
    run(['git', 'init', '-q', str(repo)], check=True)
    if config:
        (repo / '.pre-commit-config.yaml').write_text(config)
    for stage in installed:
        (repo / '.git' / 'hooks' / stage).write_text('#!/bin/sh\n')
    return repo


ORIGIN = 'git@github.com:me/proj.git'
_OURS = """\
repos:
  - repo: https://github.com/dannybrown37/git-a-grip
    rev: v0.15.0
    hooks:
      - id: protect-branch
"""
_UPSTREAM = """\
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: no-commit-to-branch
"""
_UNRELATED = """\
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: check-yaml
"""


@pytest.mark.parametrize(
    ('config', 'installed', 'expected'),
    [
        (_OURS, ('pre-push',), 'pre-commit'),
        (_UPSTREAM, ('pre-commit',), 'pre-commit'),
        # Each guard runs at its own stage; the other stage's git hook
        # being installed does not make it run.
        (_OURS, ('pre-commit',), 'uninstalled'),
        (_UPSTREAM, ('pre-push',), 'uninstalled'),
        (_OURS, (), 'uninstalled'),
        (_UNRELATED, ('pre-commit', 'pre-push'), ''),
        ('', ('pre-commit', 'pre-push'), ''),
        ('not: [valid', ('pre-commit', 'pre-push'), ''),
    ],
)
def test_local_guard(
    tmp_path: Path,
    config: str,
    installed: tuple[str, ...],
    expected: str,
) -> None:
    repo = _hooked_repo(tmp_path, config, *installed)

    assert remote.local_guard(repo) == expected


@pytest.mark.parametrize(
    ('protection', 'guard', 'shown'),
    [
        ('unknown', 'pre-commit', ' pre-commit '),
        ('unknown', 'uninstalled', ' uninstalled '),
        ('none', 'pre-commit', ' none '),
        ('classic', 'pre-commit', ' classic '),
    ],
)
def test_local_guard_fills_in_only_where_github_is_silent(
    protection: str,
    guard: str,
    shown: str,
) -> None:
    row = _quiet_row(protection=protection)
    row.local_guard = guard
    line = _row_line(remote.render([row], NOW), 'quiet')

    assert shown in line


def test_local_guard_is_amber_not_green() -> None:
    row = _quiet_row()
    row.local_guard = 'pre-commit'

    assert remote.YELLOW in remote.render([row], NOW, colour=True)


def test_inspect_records_the_local_guard(tmp_path: Path) -> None:
    repo = _hooked_repo(tmp_path, _OURS, 'pre-push')
    run: Callable[..., Any] = subprocess.run
    run(
        ['git', '-C', str(repo), 'remote', 'add', 'origin', ORIGIN],
        check=True,
    )

    row = remote.inspect(repo, _fake_gh(_responses()))

    assert row.local_guard == 'pre-commit'
