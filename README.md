# git-a-grip

Personal [pre-commit](https://pre-commit.com) hooks.

```yaml
repos:
  - repo: https://github.com/dannybrown37/git-a-grip
    rev: v0.1.0
    hooks:
      - id: commitizen-early
      - id: bump-on-push
```

Both hooks reach commitizen through `sys.executable -m commitizen` inside the
env pre-commit builds for this repo, so a consuming project needs no `cz` on
PATH, no venv and no `uv`/`uvx` of its own.

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

## `bump-on-push` (pre-push stage)

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

## Development

```bash
uv sync
uv run pytest
```

This repo eats its own dog food: both hooks are wired into its own
`.pre-commit-config.yaml`.
