# git-a-grip

Personal [pre-commit](https://pre-commit.com) hooks.

```yaml
repos:
  - repo: https://github.com/dannybrown37/git-a-grip
    rev: v0.1.0
    hooks:
      - id: commitizen-early
      - id: bump-on-push
      - id: ruff-check
      - id: ruff-format
      - id: pytest
        args: [tests/, -q]
```

The commitizen and ruff hooks reach their tool through
`sys.executable -m <tool>` inside the env pre-commit builds for this repo, so
a consuming project needs no `cz` or `ruff` on PATH, no venv and no
`uv`/`uvx` of its own. (`pytest` is the exception — see below.)

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
    rev: v0.1.0
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

Bump, tag and push, in that order, exiting 0. **Prefer this over
`bump-on-push`.** Point your push alias at it:

```bash
alias gp='uvx --from git+https://github.com/dannybrown37/git-a-grip git-release'
```

On `main` it bumps and pushes; on any other branch it just pushes, so it can
replace `git push` outright. Refuses to run against a dirty tree, and pushes
anyway when there are no bumpable commits.

This exists because a pre-push hook *cannot* do this cleanly. Git chooses
which sha to push before hooks run, so a commit created afterwards leaves two
options: cancel the push, or let git push the now-superseded sha and have it
rejected as a non-fast-forward. Both end in `error: failed to push some refs`
on top of a release that worked. Running as a command puts the bump before
the push and the problem disappears.

## `bump-on-push` (pre-push stage)

Superseded by `git-release` above; kept for repos already wired to it.



Turns the conventional commits since the last tag into a version bump,
changelog entry and tag, then pushes them — so a push and a release are the
same gesture. Configure what gets rewritten via `[tool.commitizen]` in the
consuming repo (`version_provider`, `version_files`).

Only acts on `main`, and refuses to run against a dirty tree.

**It ends with `error: failed to push some refs`, and that is expected.** The
bump commit does not exist when git decides what to push, so the hook pushes
the bumped ref itself and then fails the original push, which pointed at the
pre-bump sha. Everything is already pushed by the time you see the error; the
explanation prints just above it. Without this, the version artifacts would
sit unpushed and consumers would resolve a stale tag.

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

## Development

```bash
uv sync
uv run pytest
```

This repo eats its own dog food: both hooks are wired into its own
`.pre-commit-config.yaml`.
