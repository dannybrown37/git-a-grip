# git-a-grip

Two things, from one package:

1. **A set of [pre-commit](https://pre-commit.com) hooks** you point your
   `.pre-commit-config.yaml` at.
2. **`gag`, a CLI for managing pre-commit across all your repos** — see what
   every project pins, and pin them all to the same rev.

---

## 1. The hooks

```yaml
repos:
  - repo: https://github.com/dannybrown37/git-a-grip
    rev: v0.7.0
    hooks:
      - id: commitizen-early
      - id: ruff-check
      - id: ruff-format
      - id: embed-tree
      - id: embed-command
        args: ['--marker=help', '--command=mytool --help']
      - id: pytest
        args: [tests/, -q]
      - id: vitest
```

Nothing to install. Your project needs no `ruff`, `cz` or `uv` on PATH —
pre-commit builds the env. (`pytest`, `eslint`, `tsc` and `vitest` are the
exceptions: they must run inside *your* project's environment, so they shell
out to `uv run` / your package manager.)

| Hook | What it does for you |
| --- | --- |
| `commitizen-early` | Rejects a bad commit message in ~0.3s, instead of after the whole hook suite has run. Pair with the upstream `commitizen` hook for the cases it can't see (editor, merge, rebase). |
| `ruff-check` | `ruff check --fix`, with fixes **re-staged** — no dirty tree to `git add` and amend. |
| `ruff-format` | `ruff format`, likewise re-staged. |
| `pytest` | Your test suite, from the repo root, in your project's env. `args: ['--runner=uv run --extra api pytest', ...]` to change the runner. |
| `embed-tree` | Keeps a file tree in your README true. Drop `<!-- tree:start -->` / `<!-- tree:end -->` in, and it regenerates and re-stages on every commit. Contents come from `git ls-files`, so it's exactly what's committed. (Was `readme-tree`; the old id still works.) |
| `embed-command` | Keeps a command's output — `mytool --help`, `make help` — true in your README. Name the command in `args`; nothing is discovered and run on its own. |
| `eslint` | `eslint --fix`, re-staged, `--max-warnings=0` by default so warnings can't pile up forever. `--dir=web` for a monorepo. |
| `tsc` | Type-checks *the project*, never bare filenames — given filenames, tsc silently ignores your `tsconfig.json`. `--dir=web` for a monorepo. |
| `vitest` | `vitest run`, never the watch mode a bare `vitest` starts — that hangs the commit with no clue why. Sets `CI=true`, so a missing snapshot fails instead of being written and committed. |

Anything in `args` is passed through to the underlying tool. Pin your own
tool version with `additional_dependencies: [ruff==0.16.1]`.

`eslint`, `tsc` and `vitest` run from the repo root unless you pass `--dir=`.
If your JS lives in a subdirectory, its `eslint.config.mjs`, `tsconfig.json`
and `node_modules` resolve from *there*, so name it — and scope the hooks to
match, since files outside that subdirectory are skipped anyway:

```yaml
      - id: eslint
        args: [--dir=web]
        files: ^web/
      - id: tsc
        args: [--dir=web]
        files: ^web/
      - id: vitest
        args: [--dir=web]
        files: ^web/
```

`--runner=` means different things either side of that list. For `eslint` and
`tsc` it names only the package manager the tool is run *through*; for
`vitest` and `pytest` it replaces the command outright, because `npm test`
chooses its own test tool and appending `vitest run` to it would be wrong —
write `--runner=npm test -- --run` in full.

The two `embed-*` hooks are the exception: their `args` configure the hook
itself (`--marker=`, `--command=`, `--file=`, `--depth=`, `--exit=`). One
entry per block, each with its own `--marker`. Scope them with `files:` so a
block that changes twice a year isn't regenerated on every commit.

Full details on any hook, including the paste-ready config block:

```bash
gag hooks           # one line per hook
gag hooks pytest    # that one, in full
gag hooks --all
```

## 2. The `gag` CLI

```bash
uv tool install git-a-grip    # `gag` on PATH
uvx --from git-a-grip gag …   # or one-off
```

`gag --help` lists everything; `gag <command> --help` its options.

### `gag audit` — what does every repo pin?

Walks your project directories, stops at each git working tree, and reports
which hooks each one uses and at what rev — labelled `(behind)`, `(ahead)`,
`(unpinned)` against the version you have installed. Third-party hooks and
`repo: local` one-offs are listed too.

```bash
gag audit
gag audit ~/projects ~/work
gag audit --json | jq '.repos[] | select(.hooks == [])'
```

### `gag sync` — pin them all to one rev

The other half. Dry run by default, one line per repo (`old -> new`).

```bash
gag sync                    # dry run against the installed version
gag sync --write            # apply it
gag sync --to v0.5.0
gag sync --latest --write
gag sync --repo https://github.com/gitleaks/gitleaks --latest
```

The rewrite is textual and touches only the `rev:` line, so your comments and
formatting survive. Nothing is committed — changes land in each repo's
working tree for you to review.

### `gag hooks` — the hook reference

The table above, in full, from your installed version. Colorized for the
terminal, plain when piped. The block below is this repo's own `embed-command`
hook keeping `gag hooks` output honest:

<!-- hooks:start -->

```
git-a-grip 0.7.0 -- pre-commit hooks

Turn one on in .pre-commit-config.yaml:

repos:
  - repo: https://github.com/dannybrown37/git-a-grip
    rev: v0.7.0
    hooks:
      - id: <one of the below>
      - id: <...any number of others>

  commitizen-early  Reject a bad commit message before the slow hooks run.
  embed-command     Keep a command's output (`--help`) true in the README.
  embed-tree        Regenerate the README file tree, and re-stage it.
  eslint            Lint with the project's own eslint, re-staging fixes.
  pytest            Run the repo's tests through its own environment.
  ruff-check        Lint with `ruff check --fix`, re-staging what it fixed.
  ruff-format       Format with `ruff format`, re-staging what it rewrote.
  tsc               Type-check the project with the project's own tsc.
  vitest            Run the project's vitest suite once, never in watch mode.

gag hooks <id> for one in full, gag hooks --all for all of them.
```

<!-- hooks:end -->

---

## Running a hook by hand

The hooks aren't scripts on your PATH — `gag` is the only thing this package
installs. To run one outside pre-commit (debugging):

```bash
uv tool install 'git-a-grip[hooks]'
python -m git_a_grip.hooks ruff-check path/to/file.py
```

## Development

```bash
uv sync
uv run pytest
```

Releases are cut by CI: merge to `main`, and if lint, tests and the install
proofs pass, `cz bump` tags it and `publish.yml` uploads to PyPI. Nothing is
tagged before the checks pass.

This repo eats its own dog food — its hooks run on itself, and the tree below
is maintained by `embed-tree`.

<!-- tree:start -->

```
git-a-grip/
|-- .github/
|   `-- workflows/
|       |-- ci.yml
|       `-- publish.yml
|-- src/
|   `-- git_a_grip/
|       |-- __init__.py
|       |-- audit.py
|       |-- cli.py
|       |-- commitizen_early.py
|       |-- cz.py
|       |-- doc_block.py
|       |-- embed_command.py
|       |-- embed_tree.py
|       |-- hook_docs.py
|       |-- hooks.py
|       |-- node_hooks.py
|       |-- pytest_hook.py
|       |-- restage.py
|       |-- ruff_hooks.py
|       |-- sync.py
|       `-- version.py
|-- tests/
|   |-- test_audit.py
|   |-- test_cli.py
|   |-- test_commitizen_early.py
|   |-- test_doc_block.py
|   |-- test_embed_command.py
|   |-- test_embed_tree.py
|   |-- test_hook_docs.py
|   |-- test_hooks.py
|   |-- test_node_hooks.py
|   |-- test_packaging.py
|   |-- test_pytest_hook.py
|   |-- test_restage.py
|   |-- test_ruff_hooks.py
|   |-- test_sync.py
|   `-- test_version.py
|-- .gitignore
|-- .pre-commit-config.yaml
|-- .pre-commit-hooks.yaml
|-- .ruff.toml
|-- CHANGELOG.md
|-- CLAUDE.md
|-- LICENSE
|-- pyproject.toml
|-- README.md
`-- uv.lock
```

<!-- tree:end -->
