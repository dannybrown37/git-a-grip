"""Tests for `gag privacy`, the terms-file management command."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from git_a_grip import pick, privacy, privacy_terms

if TYPE_CHECKING:
    from pathlib import Path

BAD_ARGS_CODE = 2


@pytest.fixture
def tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the run look interactive, and keep fzf out of the tests."""
    monkeypatch.setattr(pick, 'interactive', lambda: True)
    monkeypatch.setattr(pick.shutil, 'which', lambda _: None)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    monkeypatch.delenv(privacy_terms.ENV_VAR, raising=False)
    monkeypatch.setattr(privacy_terms, 'git_dir', lambda: tmp_path / '.git')
    return tmp_path


@pytest.fixture
def terms(home: Path) -> Path:  # noqa: ARG001
    path = privacy_terms.user_path()
    privacy_terms.write(path, ['dannybrown', 'widgets inc'])
    return path


class TestDispatch:
    @pytest.mark.usefixtures('home')
    def test_help_lists_every_action(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert privacy.main(['--help']) == 0

        out = capsys.readouterr().out
        for action in privacy.ACTIONS:
            assert action in out

    @pytest.mark.usefixtures('home')
    def test_an_unknown_action_says_so_and_shows_usage(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert privacy.main(['frobnicate']) == BAD_ARGS_CODE

        err = capsys.readouterr().err
        assert 'frobnicate' in err
        assert 'usage: gag privacy' in err

    @pytest.mark.usefixtures('home')
    def test_an_unknown_option_says_so(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert privacy.main(['list', '--verbose']) == BAD_ARGS_CODE

        assert '--verbose' in capsys.readouterr().err

    @pytest.mark.usefixtures('home')
    def test_the_version_flag_answers_here_too(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from git_a_grip import version

        assert privacy.main(['--version']) == 0

        out = capsys.readouterr().out.strip()
        assert out == version.installed_version()

    @pytest.mark.usefixtures('terms')
    def test_a_bare_run_off_a_tty_prints_status_and_usage(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert privacy.main([]) == 0

        out = capsys.readouterr().out
        assert '2 terms' in out
        assert 'usage: gag privacy' in out

    @pytest.mark.usefixtures('terms', 'tty')
    def test_a_bare_run_on_a_tty_offers_the_actions(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        chosen = list(privacy.ACTION_HELP).index('list') + 1
        monkeypatch.setattr('builtins.input', lambda: str(chosen))

        assert privacy.main([]) == 0

        captured = capsys.readouterr()
        assert 'da******wn' in captured.out
        assert 'gag privacy list' in captured.err

    @pytest.mark.usefixtures('terms', 'tty')
    def test_declining_the_action_picker_is_just_status(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr('builtins.input', lambda: '')

        assert privacy.main([]) == 0

        assert 'da******wn' not in capsys.readouterr().out

    def test_the_privacy_command_is_on_the_gag_dispatcher(self) -> None:
        from git_a_grip import cli

        assert cli.COMMANDS['privacy'][0] is privacy.main


class TestStatus:
    @pytest.mark.usefixtures('home')
    def test_no_file_says_nothing_is_being_checked(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert privacy.main([]) == 0

        out = capsys.readouterr().out
        assert 'nothing is being checked' in out
        assert str(privacy_terms.user_path()) in out

    def test_status_reports_the_path_and_a_count_but_no_terms(
        self,
        terms: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert privacy.main(['status']) == 0

        out = capsys.readouterr().out
        assert str(terms) in out
        assert '2 terms' in out
        assert 'dannybrown' not in out

    @pytest.mark.usefixtures('home')
    def test_an_empty_file_says_nothing_is_being_checked(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        privacy_terms.write(privacy_terms.user_path(), [])

        assert privacy.main([]) == 0

        assert 'nothing is being checked' in capsys.readouterr().out


class TestList:
    @pytest.mark.usefixtures('terms')
    def test_terms_are_masked_by_default(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert privacy.main(['list']) == 0

        out = capsys.readouterr().out
        assert 'da******wn' in out
        assert 'dannybrown' not in out

    @pytest.mark.usefixtures('terms')
    def test_reveal_prints_them_in_full(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert privacy.main(['list', '--reveal']) == 0

        assert 'dannybrown' in capsys.readouterr().out


class TestPath:
    def test_path_prints_the_file_and_nothing_else(
        self,
        terms: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert privacy.main(['path']) == 0

        assert capsys.readouterr().out == f'{terms}\n'

    @pytest.mark.usefixtures('home')
    def test_path_fails_when_there_is_no_file(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert privacy.main(['path']) == 1

        assert capsys.readouterr().out == ''


class TestAdd:
    @pytest.mark.usefixtures('home')
    def test_a_term_lands_in_the_user_file(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert privacy.main(['add', 'acme corp']) == 0

        assert privacy_terms.read(privacy_terms.user_path()) == ['acme corp']
        assert 'acme corp' not in capsys.readouterr().out

    def test_repo_writes_to_the_git_dir_instead(self, home: Path) -> None:
        assert privacy.main(['add', '--repo', 'acme corp']) == 0

        assert privacy_terms.read(home / '.git/privacy-terms') == ['acme corp']
        assert not privacy_terms.user_path().exists()

    def test_the_env_var_is_written_to_when_it_is_what_is_read(
        self,
        home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # A write that ignored the env var would land on the user file,
        # which the env var outranks -- the term would be inert.
        target = home / 'from-env'
        monkeypatch.setenv(privacy_terms.ENV_VAR, str(target))

        assert privacy.main(['add', 'acme']) == 0

        assert privacy_terms.read(target) == ['acme']
        assert not privacy_terms.user_path().exists()

    def test_a_term_joins_the_repo_file_when_that_is_the_one_in_force(
        self,
        home: Path,
    ) -> None:
        # Creating a user file here would outrank the .git one and silently
        # retire every term already in it.
        repo_file = home / '.git/privacy-terms'
        privacy_terms.write(repo_file, ['widgets'])

        assert privacy.main(['add', 'acme']) == 0

        assert privacy_terms.read(repo_file) == ['widgets', 'acme']
        assert not privacy_terms.user_path().exists()

    def test_terms_file_beats_both(self, home: Path) -> None:
        target = home / 'chosen'

        assert privacy.main([f'--terms-file={target}', 'add', 'acme']) == 0

        assert privacy_terms.read(target) == ['acme']

    def test_a_duplicate_is_reported_not_written_twice(
        self,
        terms: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert privacy.main(['add', 'DANNYBROWN']) == 0

        assert 'already there' in capsys.readouterr().out
        assert privacy_terms.read(terms) == ['dannybrown', 'widgets inc']

    @pytest.mark.usefixtures('home')
    def test_a_short_term_is_refused_with_a_way_forward(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert privacy.main(['add', 'ab']) == BAD_ARGS_CODE

        err = capsys.readouterr().err
        assert '--force' in err
        # Even the rejection must not echo the term it rejected.
        assert 'ab' not in err.replace('--force', '')

    @pytest.mark.usefixtures('home')
    def test_force_keeps_a_short_term(self) -> None:
        assert privacy.main(['add', '--force', 'ab']) == 0

        assert privacy_terms.read(privacy_terms.user_path()) == ['ab']

    @pytest.mark.usefixtures('home')
    def test_no_term_off_a_tty_refuses_rather_than_hanging(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(privacy.sys.stdin, 'isatty', lambda: False)

        assert privacy.main(['add']) == BAD_ARGS_CODE

        assert 'arguments' in capsys.readouterr().err

    @pytest.mark.usefixtures('home', 'tty')
    def test_a_prompted_term_is_added(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # input, not getpass: a term with a typo protects nothing, so the
        # interactive path shows you what you typed.
        answers = iter(['acme corp', ''])
        monkeypatch.setattr('builtins.input', lambda: next(answers))

        assert privacy.main(['add']) == 0

        assert privacy_terms.read(privacy_terms.user_path()) == ['acme corp']

    @pytest.mark.usefixtures('home', 'tty')
    def test_a_prompted_run_echoes_the_line_that_skips_the_prompt(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        answers = iter(['acme corp', ''])
        monkeypatch.setattr('builtins.input', lambda: next(answers))

        assert privacy.main(['--repo', 'add']) == 0

        # Quoted, flags kept: the line has to survive a paste.
        assert "gag privacy add --repo 'acme corp'" in capsys.readouterr().err


class TestRemove:
    def test_a_term_goes(self, terms: Path) -> None:
        assert privacy.main(['remove', 'dannybrown']) == 0

        assert privacy_terms.read(terms) == ['widgets inc']

    @pytest.mark.usefixtures('terms')
    def test_a_term_that_was_not_there_is_reported(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert privacy.main(['remove', 'nope']) == 0

        assert '1 not found' in capsys.readouterr().err

    @pytest.mark.usefixtures('terms')
    def test_no_term_off_a_tty_names_the_argument(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert privacy.main(['remove']) == BAD_ARGS_CODE

        err = capsys.readouterr().err
        assert 'arguments' in err
        assert 'usage: gag privacy' in err

    @pytest.mark.usefixtures('terms', 'tty')
    def test_no_term_offers_the_terms_that_exist(
        self,
        terms: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr('builtins.input', lambda: '2')

        assert privacy.main(['remove']) == 0

        assert privacy_terms.read(terms) == ['dannybrown']
        assert "gag privacy remove 'widgets inc'" in capsys.readouterr().err

    @pytest.mark.usefixtures('terms', 'tty')
    def test_declining_the_picker_changes_nothing(
        self,
        terms: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr('builtins.input', lambda: '')

        assert privacy.main(['remove']) == 0

        assert privacy_terms.read(terms) == ['dannybrown', 'widgets inc']


class TestCheck:
    @pytest.mark.usefixtures('terms')
    def test_a_clean_file_passes(self, tmp_path: Path) -> None:
        target = tmp_path / 'clean.txt'
        target.write_text('nothing to see\n')

        assert privacy.main(['check', str(target)]) == 0

    @pytest.mark.usefixtures('terms')
    def test_a_hit_fails_and_names_the_line_but_not_the_term(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        target = tmp_path / 'dirty.txt'
        target.write_text('fine\nauthored by DannyBrown\n')

        assert privacy.main(['check', str(target)]) == 1

        out = capsys.readouterr().out
        assert f'{target}:2' in out
        assert 'da******wn' in out
        assert 'DannyBrown' not in out

    @pytest.mark.usefixtures('terms')
    def test_stdin_is_the_default_source(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(
            privacy.sys,
            'stdin',
            _Stdin('hello dannybrown\n'),
        )

        assert privacy.main(['check']) == 1

        assert '-:1' in capsys.readouterr().out

    @pytest.mark.usefixtures('terms', 'tty')
    def test_on_a_tty_the_repo_files_are_offered_rather_than_stdin(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Reading a terminal here is the hang that looks like a hang.
        target = tmp_path / 'dirty.txt'
        target.write_text('authored by dannybrown\n')
        monkeypatch.setattr(privacy, '_tracked_files', lambda: [str(target)])
        monkeypatch.setattr('builtins.input', lambda: '1')

        assert privacy.main(['check']) == 1

        captured = capsys.readouterr()
        assert f'{target}:1' in captured.out
        assert f'gag privacy check {target}' in captured.err

    @pytest.mark.usefixtures('terms', 'tty')
    def test_declining_the_file_picker_does_not_fall_back_to_stdin(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(privacy, '_tracked_files', lambda: ['a.txt'])
        monkeypatch.setattr('builtins.input', lambda: '')
        monkeypatch.setattr(privacy.sys, 'stdin', _Stdin('dannybrown\n'))

        assert privacy.main(['check']) == 0

    @pytest.mark.usefixtures('terms')
    def test_word_mode_is_passed_through(
        self,
        tmp_path: Path,
    ) -> None:
        target = tmp_path / 'sub.txt'
        target.write_text('dannybrownstone\n')

        assert privacy.main(['check', str(target)]) == 1
        assert privacy.main(['check', '--word', str(target)]) == 0

    @pytest.mark.usefixtures('home')
    def test_no_terms_checks_nothing_and_does_not_fail(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        target = tmp_path / 'any.txt'
        target.write_text('dannybrown\n')

        assert privacy.main(['check', str(target)]) == 0

        assert 'nothing to check against' in capsys.readouterr().err

    @pytest.mark.usefixtures('terms')
    def test_an_unreadable_file_is_an_argument_error(
        self,
        tmp_path: Path,
    ) -> None:
        assert privacy.main(['check', str(tmp_path / 'nope')]) == BAD_ARGS_CODE


class _Stdin:
    """Just enough stdin for `check` to read from."""

    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        return self._text

    def isatty(self) -> bool:
        return False
