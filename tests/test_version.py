"""Tests for version parsing and comparison."""

from __future__ import annotations

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
