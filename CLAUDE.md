# Working in this repo

## Docs are part of the change, not a follow-up

This package's whole thesis is that documentation which drifts is worse than
none. A change that leaves the docs behind is not finished, and "I'll mention
it in the summary" is not documenting it.

**Adding, renaming, or changing a hook touches six places.** Do all six in the
same change:

1. `.pre-commit-hooks.yaml` — the `id`, `name`, `description`, `entry`
2. `src/git_a_grip/hooks.py` — an entry in `HOOKS`
3. `src/git_a_grip/hook_docs.py` — a `HookDoc` in `DOCS`, whose `description`
   is verbatim from the yaml (a test enforces it)
4. `README.md` — **both** the copy-paste config block under "1. The hooks"
   *and* the table row below it. Missing either one is the failure mode that
   prompted this file.
5. `tests/` — the hook's own test module
6. `.pre-commit-config.yaml` — dogfood it on this repo, unless it genuinely
   does not apply here

Changing a hook's *flags* or behaviour means revisiting 3 and 4 too: the
`notes` in `DOCS` and the README prose about `args` are documentation of the
interface, and they go stale the same way.

For the `gag` commands, the equivalent set is `cli.COMMANDS`, the command
module's docstring, and the README section for it.

## Renaming a shipped id

Never break a consuming repo's config. A renamed hook id keeps its old name in
`hooks.ALIASES`, which dispatches to the new one and prints a line saying it
moved. `tests/test_packaging.py` asserts aliases point at live hooks and never
leak back into `.pre-commit-hooks.yaml` or `gag hooks`.

## Structural rules the tests already enforce

Read `tests/test_packaging.py` before touching packaging — it is the written
form of these:

- `gag` is the only thing on a person's PATH. Hooks are reached through
  `python -m git_a_grip.hooks <id>`, never `[project.scripts]`.
- Hook-only tools (ruff) go in `additional_dependencies` per hook, never in
  base `dependencies`. Keep the pin identical to the `hooks` extra.
- Every `entry:` dispatches to a hook in `HOOKS`, and every hook in `HOOKS` is
  reachable from some `entry:`. No dead ends in either direction.

## Conventions

- **Comments explain why, not what.** Match the surrounding density: this
  codebase carries module docstrings that argue for the design and inline
  comments that name the failure being avoided. A new module without that
  reads as unfinished here.
- **A hook that rewrites a file re-stages it** through `restage.add`, and
  exits 0 — the fix is already in the commit, so failing would only make the
  author run the same command twice. Non-zero is for what the hook cannot fix
  on its own.
- **Never execute what you discovered.** `embed-command` runs the command
  named in `args` and nothing else; scanning the tree for executables to run
  is not a convenience this package offers.
- Line length 79, single quotes, full ruff config in `.ruff.toml`.

## Commands

```bash
uv run pytest -q
uv run ruff check --fix src tests && uv run ruff format src tests
uv run pre-commit run --all-files
```

## Releases — hands off

`cz bump` and CI own `CHANGELOG.md`, the version in `pyproject.toml`, and the
tags. Never edit those by hand.

**A version string in the docs is commitizen's job, not a hook's.** The bump
runs in CI, in a commit no pre-commit hook ever sees, and that commit is the
one the tag lands on — so a hook would leave every *released* doc a version
behind, stale in precisely the copy people paste. Add the file to
`[tool.commitizen] version_files` instead, and let
`test_the_readme_pins_the_version_this_repo_actually_is` notice if it stops
matching. The same reasoning rules out an `embed-version` hook. Conventional commit messages are required (the
`commitizen-early` hook rejects the rest before anything slow runs).

## Gotchas found the hard way

- pre-commit **shlex-splits `entry:`**, so an argument containing spaces must
  be quoted there: `"--command=uv run gag hooks"`. Values in `args:` are
  already separate list items and need no quoting.
- Markers inside a ``` fence are examples, not slots — `doc_block._marker_line`
  skips fenced blocks precisely because this README documents its own markers.
