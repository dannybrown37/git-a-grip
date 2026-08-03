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
    rev: v0.5.0
    hooks:
      - id: commitizen-early
      - id: ruff-check
      - id: ruff-format
      - id: readme-tree
      - id: pytest
        args: [tests/, -q]
```

Nothing to install. Your project needs no `ruff`, `cz` or `uv` on PATH —
pre-commit builds the env. (`pytest`, `eslint` and `tsc` are the exceptions:
they must run inside *your* project's environment, so they shell out to
`uv run` / your package manager.)

| Hook | What it does for you |
| --- | --- |
| `commitizen-early` | Rejects a bad commit message in ~0.3s, instead of after the whole hook suite has run. Pair with the upstream `commitizen` hook for the cases it can't see (editor, merge, rebase). |
| `ruff-check` | `ruff check --fix`, with fixes **re-staged** — no dirty tree to `git add` and amend. |
| `ruff-format` | `ruff format`, likewise re-staged. |
| `pytest` | Your test suite, from the repo root, in your project's env. `args: ['--runner=uv run --extra api pytest', ...]` to change the runner. |
| `readme-tree` | Keeps a file tree in your README true. Drop `<!-- tree:start -->` / `<!-- tree:end -->` in, and it regenerates and re-stages on every commit. Contents come from `git ls-files`, so it's exactly what's committed. |
| `eslint` | `eslint --fix`, re-staged, `--max-warnings=0` by default so warnings can't pile up forever. |
| `tsc` | Type-checks *the project*, never bare filenames — given filenames, tsc silently ignores your `tsconfig.json`. |

Anything in `args` is passed through to the underlying tool. Pin your own
tool version with `additional_dependencies: [ruff==0.16.1]`.

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

### `gag release` — bump, tag, push

For repos that release from a laptop rather than from CI. On `main` it bumps
and pushes; on any other branch it just pushes, so it can replace `git push`.
Refuses to run on a dirty tree. Configure the bump via `[tool.commitizen]` in
the target repo.

```bash
alias release='uvx --from git-a-grip gag release'
```

(A pre-push hook cannot do this: git picks the sha to push before hooks run,
so a commit made during the hook is either cancelled or rejected as
non-fast-forward. As a command, the bump simply happens first.)

### `gag hooks` — the hook reference

The table above, in full, from your installed version. Colorized for the
terminal, plain when piped.

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
is maintained by `readme-tree`.

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
|       |-- hook_docs.py
|       |-- hooks.py
|       |-- node_hooks.py
|       |-- pytest_hook.py
|       |-- readme_tree.py
|       |-- release.py
|       |-- restage.py
|       |-- ruff_hooks.py
|       |-- sync.py
|       `-- version.py
|-- tests/
|   |-- test_audit.py
|   |-- test_cli.py
|   |-- test_commitizen_early.py
|   |-- test_hook_docs.py
|   |-- test_hooks.py
|   |-- test_node_hooks.py
|   |-- test_packaging.py
|   |-- test_pytest_hook.py
|   |-- test_readme_tree.py
|   |-- test_release.py
|   |-- test_restage.py
|   |-- test_ruff_hooks.py
|   |-- test_sync.py
|   `-- test_version.py
|-- .gitignore
|-- .pre-commit-config.yaml
|-- .pre-commit-hooks.yaml
|-- .ruff.toml
|-- CHANGELOG.md
|-- LICENSE
|-- pyproject.toml
|-- README.md
`-- uv.lock
```

<!-- tree:end -->
