"""Tests for version parsing and comparison."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from git_a_grip import version


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [('0.3.1', 'v0.3.1'), ('v0.3.1', 'v0.3.1')],
)
def test_as_rev_adds_one_v_only(raw: str, expected: str) -> None:
    assert version.as_rev(raw) == expected


def test_as_version_strips_the_tag_prefix() -> None:
    assert version.as_version('v1.2.3') == '1.2.3'
    assert version.as_version('1.2.3') == '1.2.3'


@pytest.mark.parametrize(
    ('left', 'right', 'expected'),
    [
        ('v0.3.1', '0.3.1', 0),
        ('v0.3.0', 'v0.3.1', -1),
        ('v0.4.0', 'v0.3.9', 1),
        ('v0.3', 'v0.3.1', -1),
        ('main', 'v0.1.0', -1),
        ('', 'v0.1.0', -1),
    ],
)
def test_compare_orders_versions(left: str, right: str, expected: int) -> None:
    assert version.compare(left, right) == expected


def test_prerelease_suffix_does_not_break_parsing() -> None:
    assert version.parts('v1.2.3rc1') == (1, 2, 3)


def test_installed_version_is_a_string() -> None:
    assert isinstance(version.installed_version(), str)


def _write_pyproject(root: Path, name: str, declared: str) -> None:
    root.joinpath('pyproject.toml').write_text(
        f'[project]\nname = "{name}"\nversion = "{declared}"\n',
    )


def test_this_checkout_reports_the_version_it_declares() -> None:
    # An editable install's dist-info goes stale the moment `cz bump` lands,
    # and every consumer of this string -- the README block, `gag sync`'s
    # pins -- would then write that stale number into someone else's repo.
    root = Path(__file__).resolve().parents[1]
    declared = tomllib.loads(
        root.joinpath('pyproject.toml').read_text(),
    )['project']['version']

    assert version.installed_version() == declared


def test_a_checkout_outranks_the_installed_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_pyproject(tmp_path, version.DIST_NAME, '9.9.9')
    monkeypatch.setattr(version, '_SOURCE_ROOT', tmp_path)

    assert version.installed_version() == '9.9.9'


def test_someone_elses_pyproject_is_not_this_package(tmp_path: Path) -> None:
    # A wheel in site-packages can sit under any project's tree. Only a
    # pyproject that names *this* distribution describes this code.
    _write_pyproject(tmp_path, 'some-other-thing', '9.9.9')

    assert version.version_from_source(tmp_path) is None


def test_no_pyproject_means_no_source_version(tmp_path: Path) -> None:
    assert version.version_from_source(tmp_path) is None


def test_an_unparseable_pyproject_is_not_fatal(tmp_path: Path) -> None:
    # Reporting a version is never the caller's actual errand.
    tmp_path.joinpath('pyproject.toml').write_text('[project\n')

    assert version.version_from_source(tmp_path) is None
