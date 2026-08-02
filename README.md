# git-a-grip

Personal [pre-commit](https://pre-commit.com) hooks.

```yaml
repos:
  - repo: https://github.com/dannybrown37/git-a-grip
    rev: v0.3.1
    hooks:
      - id: commitizen-early
      - id: ruff-check
      - id: ruff-format
      - id: pytest
        args: [tests/, -q]
```

The commitizen and ruff hooks reach their tool through
`sys.executable -m <tool>` inside the env pre-commit builds for this repo, so
a consuming project needs no `cz` or `ruff` on PATH, no venv and no
`uv`/`uvx` of its own. (`pytest` is the exception — see below.)

Each hook pays only for what it uses: commitizen is a dependency of the
package, while ruff is declared by the two ruff hooks themselves, through
`additional_dependencies` in `.pre-commit-hooks.yaml`. You still pass
nothing. Pin your own ruff by setting `additional_dependencies:
[ruff==x.y.z]` on the hook.

## `commitizen-early` (pre-commit stage)

Rejects a non-conventional commit message in about a third of a second,
instead of after the whole slow hook suite has run.

Git runs `pre-commit` -> `prepare-commit-msg` -> editor -> `commit-msg` as
separate invocations, so a `stages: [commit-msg]` commitizen hook can only
ever fail *after* your tests. Nothing in `.pre-commit-config.yaml` reorders
that. This hook instead recovers the message from the `git commit` process's
own argv while the pre-commit stage is still running, and checks it first.

Pair it with the upstream `commitizen` hook, which still catches the cases
argv cannot reach (interactive editor, merge, rebase) — this one exits 0 and
defers whenever it finds no message:

```yaml
  - repo: https://github.com/dannybrown37/git-a-grip
    rev: v0.3.1
    hooks:
      - id: commitizen-early

  - repo: https://github.com/commitizen-tools/commitizen
    rev: v4.17.0
    hooks:
      - id: commitizen
        stages: [commit-msg]
```

Put it first and give it `fail_fast: true` if you want it to short-circuit
the rest of the stage.

## `git-release` (command, not a hook)

Bump, tag and push, in that order, exiting 0. For repos that release from a
laptop rather than from CI. Give it an alias that says what it does — not
`gp`, which reads as `git push` right up until it publishes something:

```bash
alias release='uvx --from git-a-grip git-release'
```

This repo itself no longer uses it: releases here are cut by CI once the
checks on `main` pass (see below). The command remains for projects with no
such pipeline, where the alternative is remembering the four commands by
hand.

On `main` it bumps and pushes; on any other branch it just pushes, so it can
replace `git push` outright. Refuses to run against a dirty tree, and pushes
anyway when there are no bumpable commits.

This exists because a pre-push hook *cannot* do this cleanly. Git chooses
which sha to push before hooks run, so a commit created afterwards leaves two
options: cancel the push, or let git push the now-superseded sha and have it
rejected as a non-fast-forward. Both end in `error: failed to push some refs`
on top of a release that worked. Running as a command puts the bump before
the push and the problem disappears.

Configure what the bump rewrites via `[tool.commitizen]` in the consuming
repo (`version_provider`, `version_files`).

> A `bump-on-push` pre-push hook did this up to v0.2.1 and was removed in
> v0.3.0 for the reason above. If you pin an older rev, that hook still
> exists there; on upgrading, drop `- id: bump-on-push` and use this command.

## `ruff-check` and `ruff-format` (pre-commit stage)

`ruff check --fix` and `ruff format`, with the fixes **re-staged** so they are
part of the commit you just made rather than a dirty working tree you have to
`git add` and amend. Only the violations ruff could not fix stop the commit,
via ruff's own exit code.

Pass ruff's flags through `args`:

```yaml
      - id: ruff-check
        args: [--config, .ruff.toml]
```

`--force-exclude` is always passed, so the `exclude` in your ruff config still
applies to the paths pre-commit hands over explicitly. The re-staged set is
narrowed by content digest — a file ruff did not change is never touched, and
because pre-commit stashes unstaged changes while a hook runs, re-adding a
file cannot sweep in an edit you deliberately left unstaged.

The ruff version is this repo's pinned dependency. To hold a repo at a
different one:

```yaml
      - id: ruff-format
        additional_dependencies: [ruff==0.16.1]
```

## `pytest` (pre-commit stage)

Runs the test suite from the repo root. This hook can't use the isolated env
pre-commit builds here — a test suite needs the *consuming* project's
dependencies — so it shells out to a runner that resolves that environment,
`uv run pytest` by default. Everything else in `args` goes to pytest:

```yaml
      - id: pytest
        args: [tests/, -q]

      - id: pytest
        args: ['--runner=uv run --extra api pytest', tests/, -q]
```

It runs from the repo root regardless of where git was invoked, and drops the
`VIRTUAL_ENV`/`PYTHONPATH` that pre-commit exports for its own hook env —
which would otherwise point the runner at an environment holding none of your
project's dependencies. Narrow when it runs with `files:` (default
`^(src/|tests/).*`).

## `pre-commit-audit` (command, not a hook)

Audit every local repo's pre-commit setup at once, so a hook that drifted or
never got installed shows up as a line rather than a surprise:

```bash
uvx --from git-a-grip pre-commit-audit
```

It walks the given trees (default: this repo's sibling directories), stops at
each git working tree, and reports four things: which of this repo's hooks
each project uses and the `rev` it pins, third-party hooks grouped by source
repo and rev, one-off `repo: local` hooks with their entry, and repos with no
usable config at all. `--json` emits the same data unformatted.

```bash
pre-commit-audit ~/projects ~/work
pre-commit-audit --json | jq '.[] | select(.hooks == [])'
```

## Installing the commands

The hooks need no installation — pre-commit builds this repo an isolated env
from the `rev` you pin. The two commands (`git-release`, `pre-commit-audit`)
are ordinary console scripts, published to PyPI:

```bash
uvx --from git-a-grip pre-commit-audit    # one-off
uv tool install git-a-grip                # both commands, on PATH
```

That install carries only what the commands import — commitizen and pyyaml —
not the ruff the hooks use. To run the hook entry points by hand as well, ask
for the extra:

```bash
uv tool install 'git-a-grip[hooks]'
```

Straight from a tag works too, and is the way to run something not yet
released:

```bash
uvx --from git+https://github.com/dannybrown37/git-a-grip@v0.3.1 git-release
```

## Releasing

Merge to `main`. That is the whole gesture.

`ci.yml` runs lint, tests and the install proofs on the merged commit; only
if they all pass does its `bump` job run `cz bump`, which writes the version
and changelog, commits, and tags. Pushing that tag triggers `publish.yml`,
which builds and uploads to PyPI via trusted publishing. A push with no
bumpable commits (docs, chores) ends after the checks and releases nothing.

Nothing is tagged before the checks pass, so a red build cannot leave a
version number stranded on a release that never shipped.

## Development

```bash
uv sync
uv run pytest
```

This repo eats its own dog food: both hooks are wired into its own
`.pre-commit-config.yaml`.
