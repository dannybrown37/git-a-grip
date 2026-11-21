"""Tests for the hook that blocks a commit adding a private term."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from git_a_grip import privacy_hook, privacy_terms

if TYPE_CHECKING:
    from pathlib import Path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603
        ['git', *args],  # noqa: S607
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real repo with one commit, cwd'd into, with terms configured.

    The diff parsing is the part worth testing against git itself rather
    than against a fixture of what git's output was believed to look like.
    """
    _git(tmp_path, 'init', '--initial-branch=main')
    _git(tmp_path, 'config', 'user.email', 'test@example.com')
    _git(tmp_path, 'config', 'user.name', 'Test')
    (tmp_path / 'kept.txt').write_text('first line\n')
    _git(tmp_path, 'add', 'kept.txt')
    _git(tmp_path, 'commit', '-m', 'feat: first')

    terms = tmp_path / 'terms'
    terms.write_text('dannybrown\nwidgets inc\n')
    terms.chmod(0o600)
    monkeypatch.setenv(privacy_terms.ENV_VAR, str(terms))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _stage(repo: Path, name: str, text: str) -> None:
    (repo / name).write_text(text)
    _git(repo, 'add', name)


LONG = ''.join(f'line {n}\n' for n in range(20))


def _rename_with_edit(repo: Path, added: str) -> None:
    """Stage a move that git reports as R, not as a delete plus an add."""
    _stage(repo, 'long.txt', LONG)
    _git(repo, 'commit', '-m', 'feat: long')
    _git(repo, 'mv', 'long.txt', 'moved.txt')
    _stage(repo, 'moved.txt', LONG + added)


class TestAddedLines:
    def test_a_new_file_reports_every_line_with_its_number(
        self,
        repo: Path,
    ) -> None:
        _stage(repo, 'new.txt', 'one\ntwo\nthree\n')

        assert privacy_hook.added_lines([]) == [
            ('new.txt', 1, 'one'),
            ('new.txt', 2, 'two'),
            ('new.txt', 3, 'three'),
        ]

    def test_an_edit_reports_only_what_it_adds(self, repo: Path) -> None:
        _stage(repo, 'kept.txt', 'first line\nsecond line\n')

        assert privacy_hook.added_lines([]) == [('kept.txt', 2, 'second line')]

    def test_line_numbers_survive_several_hunks(self, repo: Path) -> None:
        _stage(repo, 'kept.txt', 'top\nfirst line\n')
        _stage(repo, 'other.txt', 'a\n')

        assert privacy_hook.added_lines([]) == [
            ('kept.txt', 1, 'top'),
            ('other.txt', 1, 'a'),
        ]

    def test_unstaged_work_is_not_read(self, repo: Path) -> None:
        (repo / 'kept.txt').write_text('first line\nnot staged\n')

        assert privacy_hook.added_lines([]) == []

    def test_a_named_path_narrows_the_diff(self, repo: Path) -> None:
        _stage(repo, 'a.txt', 'aaa\n')
        _stage(repo, 'b.txt', 'bbb\n')

        assert privacy_hook.added_lines(['b.txt']) == [('b.txt', 1, 'bbb')]

    def test_a_deleted_file_contributes_nothing(self, repo: Path) -> None:
        _git(repo, 'rm', 'kept.txt')

        assert privacy_hook.added_lines([]) == []

    def test_a_renamed_file_reports_what_the_rename_adds(
        self,
        repo: Path,
    ) -> None:
        # git reports a rename with edits as R, not M; a filter that leaves
        # R out lets a term ride in on any `git mv`.
        _rename_with_edit(repo, 'appended\n')

        assert privacy_hook.added_lines([]) == [('moved.txt', 21, 'appended')]

    def test_a_line_starting_with_plus_plus_is_content_not_a_header(
        self,
        repo: Path,
    ) -> None:
        # Added `++i;` reaches the diff as `+++i;`, which is only a file
        # header when it sits between `--- ` and the first `@@`.
        _stage(repo, 'a.c', '++i;\n++ note\n')
        _stage(repo, 'b.txt', 'b\n')

        assert privacy_hook.added_lines([]) == [
            ('a.c', 1, '++i;'),
            ('a.c', 2, '++ note'),
            ('b.txt', 1, 'b'),
        ]

    def test_content_that_is_not_utf8_is_still_read(self, repo: Path) -> None:
        (repo / 'latin1.txt').write_bytes(b'caf\xe9 ok\n')
        _git(repo, 'add', 'latin1.txt')

        [(name, number, text)] = privacy_hook.added_lines([])
        assert (name, number) == ('latin1.txt', 1)
        assert text.endswith(' ok')


class TestMain:
    def test_a_clean_commit_passes(self, repo: Path) -> None:
        _stage(repo, 'new.txt', 'nothing sensitive\n')

        assert privacy_hook.main([]) == 0

    def test_an_added_term_blocks_the_commit(
        self,
        repo: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _stage(repo, 'new.txt', 'fine\nwritten by DannyBrown\n')

        assert privacy_hook.main([]) == 1

        err = capsys.readouterr().err
        assert 'new.txt:2' in err
        assert 'gag privacy remove' in err

    def test_the_matching_line_is_never_printed(
        self,
        repo: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # The hook's output lands in scrollback and in CI logs; echoing the
        # hit would publish what the match just caught.
        _stage(repo, 'new.txt', 'written by DannyBrown\n')

        assert privacy_hook.main([]) == 1

        err = capsys.readouterr().err
        assert 'DannyBrown' not in err
        assert 'da******wn' in err

    def test_a_term_already_committed_is_not_re_flagged(
        self,
        repo: Path,
    ) -> None:
        _stage(repo, 'old.txt', 'by dannybrown\n')
        _git(repo, 'commit', '-m', 'feat: whoops')
        _stage(repo, 'old.txt', 'by dannybrown\nand a clean new line\n')

        assert privacy_hook.main([]) == 0

    def test_word_mode_is_available(self, repo: Path) -> None:
        _stage(repo, 'new.txt', 'dannybrownstone quarry\n')

        assert privacy_hook.main([]) == 1
        assert privacy_hook.main(['--word']) == 0

    def test_a_terms_file_can_be_named(self, repo: Path) -> None:
        other = repo / 'other-terms'
        other.write_text('quarry\n')
        other.chmod(0o600)
        _stage(repo, 'new.txt', 'the quarry\n')

        assert privacy_hook.main([f'--terms-file={other}']) == 1

    def test_the_report_names_the_terms_file_that_was_used(
        self,
        repo: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        other = repo / 'other-terms'
        other.write_text('quarry\n')
        other.chmod(0o600)
        _stage(repo, 'new.txt', 'the quarry\n')

        privacy_hook.main([f'--terms-file={other}'])

        assert f'The terms are in {other}.' in capsys.readouterr().err

    def test_a_term_in_a_plus_plus_line_blocks_the_commit(
        self,
        repo: Path,
    ) -> None:
        _stage(repo, 'new.c', '++dannybrown;\n')

        assert privacy_hook.main([]) == 1

    def test_a_term_added_during_a_rename_blocks_the_commit(
        self,
        repo: Path,
    ) -> None:
        _rename_with_edit(repo, 'by dannybrown\n')

        assert privacy_hook.main([]) == 1

    def test_a_term_in_non_utf8_content_blocks_the_commit(
        self,
        repo: Path,
    ) -> None:
        (repo / 'latin1.txt').write_bytes(b'caf\xe9 by dannybrown\n')
        _git(repo, 'add', 'latin1.txt')

        assert privacy_hook.main([]) == 1

    @pytest.mark.usefixtures('repo')
    def test_help_exits_clean(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert privacy_hook.main(['--help']) == 0

        assert 'usage: block-private-terms' in capsys.readouterr().out


class TestUnconfigured:
    def test_no_terms_file_warns_and_passes(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # A hard failure on a machine that never set this up is how the hook
        # gets deleted from a shared config, taking everyone's with it.
        monkeypatch.setenv(privacy_terms.ENV_VAR, str(repo / 'nothing-here'))
        monkeypatch.setattr(privacy_terms, 'user_path', lambda: repo / 'no')
        _stage(repo, 'new.txt', 'by dannybrown\n')

        assert privacy_hook.main([]) == 0

        assert 'not checked' in capsys.readouterr().err

    def test_an_empty_terms_file_also_passes(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        empty = repo / 'empty-terms'
        empty.write_text('# nothing yet\n')
        empty.chmod(0o600)
        monkeypatch.setenv(privacy_terms.ENV_VAR, str(empty))

        assert privacy_hook.main([]) == 0

    def test_a_world_readable_terms_file_fails_the_commit(
        self,
        repo: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # The opposite case: believing you are covered while the terms sit
        # in the open is worse than knowing you are not.
        (repo / 'terms').chmod(0o644)

        assert privacy_hook.main([]) == 1

        assert 'chmod 600' in capsys.readouterr().err
