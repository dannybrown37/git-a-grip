"""Tests for the privacy-terms store."""

from __future__ import annotations

import stat
from typing import TYPE_CHECKING

import pytest

from git_a_grip import privacy_terms

if TYPE_CHECKING:
    from pathlib import Path

OWNER_ONLY_FILE = 0o600
OWNER_ONLY_DIR = 0o700


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the ladder's every rung inside tmp_path."""
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    monkeypatch.delenv(privacy_terms.ENV_VAR, raising=False)
    monkeypatch.setattr(privacy_terms, 'git_dir', lambda: tmp_path / '.git')
    return tmp_path


def _write(path: Path, text: str, mode: int = 0o600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)
    return path


class TestResolve:
    @pytest.mark.usefixtures('home')
    def test_no_file_anywhere_resolves_to_nothing(self) -> None:
        assert privacy_terms.resolve() is None

    def test_the_user_config_is_found(self, home: Path) -> None:
        path = _write(home / 'config/git-a-grip/privacy-terms', 'acme\n')

        assert privacy_terms.resolve() == path

    def test_the_git_dir_is_the_last_rung(self, home: Path) -> None:
        path = _write(home / '.git/privacy-terms', 'acme\n')

        assert privacy_terms.resolve() == path

    def test_the_user_config_outranks_the_git_dir(self, home: Path) -> None:
        user = _write(home / 'config/git-a-grip/privacy-terms', 'acme\n')
        _write(home / '.git/privacy-terms', 'other\n')

        assert privacy_terms.resolve() == user

    def test_the_env_var_outranks_the_user_config(
        self,
        home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _write(home / 'config/git-a-grip/privacy-terms', 'acme\n')
        override = _write(home / 'elsewhere/terms', 'other\n')
        monkeypatch.setenv(privacy_terms.ENV_VAR, str(override))

        assert privacy_terms.resolve() == override

    def test_an_explicit_path_outranks_everything(
        self,
        home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(privacy_terms.ENV_VAR, str(home / 'env-terms'))
        explicit = _write(home / 'explicit', 'acme\n')

        assert privacy_terms.resolve(explicit) == explicit

    def test_a_named_path_that_is_missing_is_still_returned(
        self,
        home: Path,
    ) -> None:
        # Naming a file that is not there is a mistake worth a message, not
        # a silent fall through to whatever the next rung happens to hold.
        missing = home / 'nope'

        assert privacy_terms.resolve(missing) == missing


class TestRead:
    def test_terms_come_back_one_per_line(self, home: Path) -> None:
        path = _write(home / 'terms', 'acme\nwidgets inc\n')

        assert privacy_terms.read(path) == ['acme', 'widgets inc']

    def test_comments_and_blanks_are_skipped(self, home: Path) -> None:
        path = _write(home / 'terms', '# employers\n\nacme\n  \n')

        assert privacy_terms.read(path) == ['acme']

    def test_surrounding_whitespace_is_stripped(self, home: Path) -> None:
        path = _write(home / 'terms', '  acme  \n')

        assert privacy_terms.read(path) == ['acme']

    def test_a_missing_file_reads_as_empty(self, home: Path) -> None:
        assert privacy_terms.read(home / 'nope') == []

    def test_a_readable_by_others_file_is_refused(self, home: Path) -> None:
        path = _write(home / 'terms', 'acme\n', mode=0o644)

        with pytest.raises(privacy_terms.PrivacyTermsError) as excinfo:
            privacy_terms.read(path)

        assert 'chmod 600' in str(excinfo.value)

    def test_a_group_writable_file_is_refused(self, home: Path) -> None:
        path = _write(home / 'terms', 'acme\n', mode=0o660)

        with pytest.raises(privacy_terms.PrivacyTermsError):
            privacy_terms.read(path)

    def test_a_symlink_is_judged_by_its_target(self, home: Path) -> None:
        # The link's own mode is always 0o777 and says nothing; the terms
        # live in the file at the far end, and so does the exposure.
        target = _write(home / 'real/terms', 'acme\n', mode=0o600)
        link = home / 'link-terms'
        link.symlink_to(target)

        assert privacy_terms.read(link) == ['acme']

        target.chmod(0o644)
        with pytest.raises(privacy_terms.PrivacyTermsError):
            privacy_terms.read(link)


class TestWrite:
    def test_a_new_file_is_private_from_the_start(self, home: Path) -> None:
        path = home / 'nested/terms'

        privacy_terms.write(path, ['acme'])

        assert stat.S_IMODE(path.stat().st_mode) == OWNER_ONLY_FILE
        assert stat.S_IMODE(path.parent.stat().st_mode) == OWNER_ONLY_DIR

    def test_a_rewrite_keeps_the_mode(self, home: Path) -> None:
        path = _write(home / 'terms', 'acme\n')

        privacy_terms.write(path, ['acme', 'widgets'])

        assert stat.S_IMODE(path.stat().st_mode) == OWNER_ONLY_FILE
        assert privacy_terms.read(path) == ['acme', 'widgets']

    def test_no_temp_file_is_left_behind(self, home: Path) -> None:
        path = home / 'dir/terms'

        privacy_terms.write(path, ['acme'])

        assert [p.name for p in path.parent.iterdir()] == ['terms']

    def test_a_symlink_is_written_through(self, home: Path) -> None:
        target = _write(home / 'real/terms', 'acme\n')
        link = home / 'link-terms'
        link.symlink_to(target)

        privacy_terms.write(link, ['acme', 'widgets'])

        assert link.is_symlink()
        assert privacy_terms.read(target) == ['acme', 'widgets']


class TestAddAndRemove:
    def test_adding_appends(self, home: Path) -> None:
        path = home / 'terms'

        assert privacy_terms.add(path, ['acme']) == ['acme']
        assert privacy_terms.add(path, ['widgets']) == ['widgets']
        assert privacy_terms.read(path) == ['acme', 'widgets']

    def test_adding_a_duplicate_is_not_an_error_but_changes_nothing(
        self,
        home: Path,
    ) -> None:
        path = _write(home / 'terms', 'acme\n')

        assert privacy_terms.add(path, ['acme', 'ACME']) == []
        assert privacy_terms.read(path) == ['acme']

    @pytest.mark.parametrize('term', ['ab', '', '   '])
    def test_a_term_too_short_to_be_meant_is_refused(
        self,
        home: Path,
        term: str,
    ) -> None:
        with pytest.raises(privacy_terms.PrivacyTermsError):
            privacy_terms.add(home / 'terms', [term])

    def test_a_short_term_can_be_forced(self, home: Path) -> None:
        path = home / 'terms'

        assert privacy_terms.add(path, ['ab'], force=True) == ['ab']

    @pytest.mark.parametrize('term', ['a\nb', 'a\rb'])
    def test_a_term_spanning_lines_is_refused(
        self,
        home: Path,
        term: str,
    ) -> None:
        # One term per line is the whole file format; a newline inside a
        # term would silently become two terms on the next read.
        with pytest.raises(privacy_terms.PrivacyTermsError):
            privacy_terms.add(home / 'terms', [term], force=True)

    def test_removing_reports_what_was_not_there(self, home: Path) -> None:
        path = _write(home / 'terms', 'acme\nwidgets\n')

        removed, missing = privacy_terms.remove(path, ['ACME', 'nope'])

        assert removed == ['acme']
        assert missing == ['nope']
        assert privacy_terms.read(path) == ['widgets']

    def test_removing_from_a_missing_file_removes_nothing(
        self,
        home: Path,
    ) -> None:
        removed, missing = privacy_terms.remove(home / 'nope', ['acme'])

        assert (removed, missing) == ([], ['acme'])


class TestMask:
    @pytest.mark.parametrize(
        ('term', 'expected'),
        [
            ('dannybrown', 'da******wn'),
            ('acme', 'a**e'),
            ('abcd', 'a**d'),
            ('abc', '***'),
            ('ab', '**'),
        ],
    )
    def test_enough_to_recognise_not_enough_to_read(
        self,
        term: str,
        expected: str,
    ) -> None:
        assert privacy_terms.mask(term) == expected


class TestMatches:
    def test_a_substring_matches_case_insensitively(self) -> None:
        assert privacy_terms.matches('at ACME Corp', ['acme']) == ['acme']

    def test_a_clean_line_matches_nothing(self) -> None:
        assert privacy_terms.matches('nothing here', ['acme']) == []

    def test_every_matching_term_is_reported(self) -> None:
        found = privacy_terms.matches('acme widgets', ['acme', 'widgets'])

        assert found == ['acme', 'widgets']

    @pytest.mark.parametrize(
        ('text', 'expected'),
        [
            ('the acme corp', ['acme']),
            ('acme', ['acme']),
            ('acme, inc', ['acme']),
            ('acmeister', []),
            ('supermacme', []),
        ],
    )
    def test_word_mode_needs_a_boundary(
        self,
        text: str,
        expected: list[str],
    ) -> None:
        assert privacy_terms.matches(text, ['acme'], word=True) == expected

    def test_word_mode_takes_a_term_with_punctuation_literally(self) -> None:
        # A term is a string a person typed, never a regex -- `a.c` must not
        # match `abc`, or the file becomes a trap for anyone with a domain
        # name in it.
        assert privacy_terms.matches('abc', ['a.c'], word=True) == []
        assert privacy_terms.matches('a.c', ['a.c'], word=True) == ['a.c']
