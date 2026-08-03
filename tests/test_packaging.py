"""Guard the seams between pyproject.toml and .pre-commit-hooks.yaml.

Three files describe how a hook reaches its tools, and nothing but these
tests makes them agree: an `entry:` that no longer dispatches to a hook in
`git_a_grip.hooks` installs fine and fails at run time in the consumer's
repo, a script that leaks into `[project.scripts]` is one `gag --help` never
mentions, and a ruff pin that drifts between the hook and the `hooks` extra
means the two ways of running the same code run different ruffs.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((ROOT / 'pyproject.toml').read_text())
HOOKS = yaml.safe_load((ROOT / '.pre-commit-hooks.yaml').read_text())

RUFF_PIN = 'ruff>=0.6'
# Every hook goes through the dispatcher, never a console script.
PYTHON_M = 'python -m'
# Tools no command imports, so they must not be in the base dependencies.
HOOK_ONLY_TOOLS = ('ruff',)


def _requirement_names(requirements: list[str]) -> set[str]:
    return {
        req.split('>')[0].split('=')[0].split('<')[0].split('[')[0].strip()
        for req in requirements
    }


def test_gag_is_the_only_thing_installed_on_a_path() -> None:
    # One namespace, no second: `gag` is what a person types, and the hooks
    # go through `python -m` so that installing the package cannot put a
    # command on somebody's PATH that `gag --help` does not list.
    assert set(PYPROJECT['project']['scripts']) == {'gag', 'git-a-grip'}


def test_every_hook_entry_dispatches_to_a_known_hook() -> None:
    # An entry naming a hook that `git_a_grip.hooks` does not have installs
    # fine and fails at run time in the consumer's repo.
    from git_a_grip import hooks

    for hook in HOOKS:
        prefix, _, name = hook['entry'].rpartition(' ')
        assert prefix == f'{PYTHON_M} git_a_grip.hooks'
        assert name in hooks.HOOKS


def test_no_hook_dispatches_to_nothing() -> None:
    # The other direction: a hook in the dispatcher that no `entry:` reaches
    # is dead code a consumer can never run.
    from git_a_grip import hooks

    entries = {hook['entry'].rsplit(' ', 1)[1] for hook in HOOKS}

    assert set(hooks.HOOKS) == entries


def test_the_gag_scripts_are_the_same_entry_point() -> None:
    scripts = PYPROJECT['project']['scripts']

    assert scripts['gag'] == scripts['git-a-grip'] == 'git_a_grip.cli:main_cli'


def test_every_gag_subcommand_is_reachable() -> None:
    # Importing the dispatcher is the test: a subcommand whose module moved
    # would break `gag` for every command, not just its own.
    from git_a_grip import cli

    assert set(cli.COMMANDS) == {'hooks', 'audit', 'sync', 'release'}


def test_base_dependencies_carry_no_hook_only_tools() -> None:
    names = _requirement_names(PYPROJECT['project']['dependencies'])

    assert names.isdisjoint(HOOK_ONLY_TOOLS)


def test_commands_can_import_what_they_need() -> None:
    # commitizen for `gag release`, pyyaml for `gag audit`: these two are
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


def _squashed(text: str) -> str:
    return ' '.join(text.split())


def test_every_hook_is_documented_by_gag_hooks() -> None:
    # `gag hooks` is the only place a person can read what a hook does --
    # the hooks have no console scripts and `gag --help` lists commands. A
    # hook missing from DOCS is one nobody can find.
    from git_a_grip import hook_docs

    assert set(hook_docs.DOCS) == {hook['id'] for hook in HOOKS}


def test_the_documented_prose_matches_the_hook_metadata() -> None:
    # DOCS is a second copy of the yaml, because the yaml is not shipped in
    # the wheel. Copies drift; this is what stops it.
    from git_a_grip import hook_docs

    for hook in HOOKS:
        doc = hook_docs.DOCS[hook['id']]

        assert doc.name == hook['name']
        assert _squashed(doc.description) == _squashed(hook['description'])


def test_every_documented_config_block_names_its_own_hook() -> None:
    # A copy-pasted block that turns on some other hook is worse than none.
    from git_a_grip import hook_docs

    for hook_id, doc in hook_docs.DOCS.items():
        assert doc.config[0] == f'- id: {hook_id}'
