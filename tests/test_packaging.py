"""Guard the seams between pyproject.toml and .pre-commit-hooks.yaml.

Two files describe how a hook reaches its tools, and nothing but these tests
makes them agree: a hook whose `entry` is not a console script installs fine
and fails at run time in the consumer's repo, and a ruff pin that drifts
between the hook and the `hooks` extra means the two ways of running the same
code run different ruffs.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((ROOT / 'pyproject.toml').read_text())
HOOKS = yaml.safe_load((ROOT / '.pre-commit-hooks.yaml').read_text())

RUFF_PIN = 'ruff>=0.6'
# Tools no command imports, so they must not be in the base dependencies.
HOOK_ONLY_TOOLS = ('ruff',)


def _requirement_names(requirements: list[str]) -> set[str]:
    return {
        req.split('>')[0].split('=')[0].split('<')[0].split('[')[0].strip()
        for req in requirements
    }


def test_every_hook_entry_is_a_console_script() -> None:
    scripts = set(PYPROJECT['project']['scripts'])

    entries = {hook['entry'] for hook in HOOKS}

    assert entries <= scripts


def test_base_dependencies_carry_no_hook_only_tools() -> None:
    names = _requirement_names(PYPROJECT['project']['dependencies'])

    assert names.isdisjoint(HOOK_ONLY_TOOLS)


def test_commands_can_import_what_they_need() -> None:
    # commitizen for git-release, pyyaml for pre-commit-audit: these two are
    # imported by commands, so they belong in the base install.
    names = _requirement_names(PYPROJECT['project']['dependencies'])

    assert {'commitizen', 'pyyaml'} <= names


def test_ruff_hooks_declare_ruff_themselves() -> None:
    ruff_hooks = [hook for hook in HOOKS if 'ruff' in hook['id']]

    assert ruff_hooks
    for hook in ruff_hooks:
        assert hook['additional_dependencies'] == [RUFF_PIN]


def test_hooks_extra_matches_the_hook_pin() -> None:
    extra = PYPROJECT['project']['optional-dependencies']['hooks']

    assert extra == [RUFF_PIN]


def test_non_ruff_hooks_need_no_extra_dependencies() -> None:
    others = [hook for hook in HOOKS if 'ruff' not in hook['id']]

    assert others
    for hook in others:
        assert 'additional_dependencies' not in hook
