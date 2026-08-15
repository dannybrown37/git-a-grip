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
    rev: v0.12.0
    hooks:
      - id: commitizen-early
      - id: ruff-check
      - id: ruff-format
      - id: mypy
      - id: embed-tree
      - id: embed-command
        args: ['--marker=help', '--command=mytool --help']
      - id: regen-file
        args: ['--command=python scripts/build_docs.py', '--file=docs/api.md']
      - id: pytest
        args: [tests/, -q]
      - id: vitest
      - id: block-private-terms
      - id: zizmor
```

Nothing to install. Your project needs no `ruff`, `cz` or `uv` on PATH —
pre-commit builds the env. (`pytest`, `mypy`, `eslint`, `tsc` and `vitest`
are the exceptions: they must run inside *your* project's environment, so
they shell out to `uv run` / your package manager.)

| Hook | What it does for you |
| --- | --- |
| `commitizen-early` | Rejects a bad commit message in ~0.3s, instead of after the whole hook suite has run. Pair with the upstream `commitizen` hook for the cases it can't see (editor, merge, rebase). |
| `ruff-check` | `ruff check --fix`, with fixes **re-staged** — no dirty tree to `git add` and amend. |
| `ruff-format` | `ruff format`, likewise re-staged. |
| `mypy` | Type-checks *the project*, in your project's env so mypy can import your dependencies instead of reporting on the imports — and installs mypy itself via `uv run --with`, so there's no dependency group to declare or keep in step. Names no files, so what it checks is what your mypy config says — not whichever files you happened to touch. `--runner=uv run ty check` swaps the engine. |
| `pytest` | Your test suite, from the repo root, in your project's env. `args: ['--runner=uv run --extra api pytest', ...]` to change the runner. |
| `embed-tree` | Keeps a file tree in your README true. Drop `<!-- tree:start -->` / `<!-- tree:end -->` in, and it regenerates and re-stages on every commit. Contents come from `git ls-files`, so it's exactly what's committed. (Was `readme-tree`; the old id still works.) |
| `embed-command` | Keeps a command's output — `mytool --help`, `make help` — true in your README. Name the command in `args`; nothing is discovered and run on its own. |
| `regen-file` | Replaces `bash -c 'run-the-script && git add the-file'`. Runs the generator you name and re-stages the files you name — only the ones whose contents actually moved, and it fails the commit if the script quietly stopped writing one. Use `embed-command` instead when the script owns only a marked block. |
| `eslint` | `eslint --fix`, re-staged, `--max-warnings=0` by default so warnings can't pile up forever. `--dir=web` for a monorepo. |
| `tsc` | Type-checks *the project*, never bare filenames — given filenames, tsc silently ignores your `tsconfig.json`. `--dir=web` for a monorepo. |
| `block-private-terms` | Blocks a commit that *adds* a line containing one of your own private terms — an employer, a client, an internal hostname. A secret scanner can't find these; they're ordinary words, sensitive only because of who typed them. The terms live outside the tree (see [`gag privacy`](#gag-privacy--the-terms-the-block-private-terms-hook-blocks-on)), so nothing sensitive is committed to configure it. Unconfigured, it warns and passes. |
| `zizmor` | Audits your GitHub Actions workflows with [zizmor](https://docs.zizmor.sh) — the `pull_request_target` that checks out the PR head, the `${{ github.event.* }}` interpolated straight into a `run:` block. Checks the workflows the commit touched, and brings its own zizmor. `args: [--fix]` if you want it to rewrite, and the rewrite is re-staged like every other fix here. |
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
`vitest`, `pytest` and `mypy` it replaces the command outright, because `npm
test` chooses its own test tool and appending `vitest run` to it would be
wrong — write `--runner=npm test -- --run` in full.

The `embed-*` hooks and `regen-file` are the exception: their `args` configure
the hook itself (`--marker=`, `--command=`, `--file=`, `--depth=`, `--exit=`).
One entry per block, each with its own `--marker`; `regen-file` takes
`--file=` once per file its script writes. In all three the command is only
ever the one you wrote down — nothing is discovered and run on its own, and
there is no shell, so `&&` is an argument rather than a second command. Scope
them with `files:` so a block that changes twice a year isn't regenerated on
every commit.

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

Without `--to` or `--latest` the target is the version you have *installed*,
which is only a stand-in for the current release. So that run also asks the
source for its newest tag and warns on stderr when your install is behind it:

```
sync: installed v0.7.0, but v0.8.0 is the newest tag at <repo>.
      Re-run with --latest to pin v0.8.0 instead, or upgrade git-a-grip.
```

The plan is still printed — the warning says the target may not be the one
you want, not that the answer is useless. An unreachable remote skips the
check silently, so `gag sync` still works offline.

### `gag privacy` — the terms the `block-private-terms` hook blocks on

A secret scanner finds credentials. It cannot find the strings that are only
sensitive because of *who typed them* — an employer, a client, an internal
hostname, a relative's name. Those are yours, so they never live in the repo:

```bash
gag privacy                         # status, then pick an action
gag privacy add                     # prompts, echoing, so typos show
gag privacy add "acme corp"         # or as an argument, for scripts
gag privacy list                    # masked: `da******wn`
gag privacy list --reveal           # in full, when you mean it
gag privacy path                    # the file in use, for `$EDITOR "$(...)"`
gag privacy check some_file.py      # what the hook would flag, no commit
gag privacy check                   # or pick the file from the repo
gag privacy remove                  # pick from the terms you have
gag privacy remove "acme corp"
```

Anything it needs and wasn't given, it asks for — `fzf` when you have it,
a numbered list when you don't (`GAG_NO_FZF=1` forces the list). Every
prompt has a flag that skips it, and an interactive run finishes by
printing the one-liner you could have typed:

```console
$ gag privacy remove
  1) acme corp
  2) dannybrown
remove: (numbers, comma-separated, blank to cancel) 1
Removed 1 from /home/you/.config/git-a-grip/privacy-terms

Next time, in one line:
  gag privacy remove 'acme corp'
```

Off a terminal nothing prompts: it names the argument that was missing and
exits 2, so a CI job fails in a line instead of hanging until its timeout.

Terms are read from the first of these that exists: `--terms-file=`,
`$GAG_PRIVACY_TERMS_FILE`, `$XDG_CONFIG_HOME/git-a-grip/privacy-terms`, then
`<repo>/.git/privacy-terms`. The third is the one to use — one file, every
repo on the machine covered. `--repo` writes to the fourth instead, for a
term that belongs to one project and shouldn't follow you around; note that
deleting that clone deletes the terms with it.

The file is line-delimited text, `#` comments allowed, and it is read
literally — never sourced. `gag privacy` creates it `0600` in a `0700`
directory and **refuses to read one the rest of the machine can read**: a
terms file at `0644` leaves you believing you're covered while the terms sit
in the open. A symlinked file is followed and judged at the far end, so
keeping the real file in your dotfiles works.

Nothing here prints a term in full unless you ask. `add` reports a count,
`list` masks, and the hook names the file and line but never the match —
this output goes to scrollback and into CI logs.

### `gag hooks` — the hook reference

The table above, in full, from your installed version. Colorized for the
terminal, plain when piped. The block below is this repo's own `embed-command`
hook keeping `gag hooks` output honest:

<!-- hooks:start -->

```
git-a-grip -- pre-commit hooks

Turn one on in .pre-commit-config.yaml:

repos:
  - repo: https://github.com/dannybrown37/git-a-grip
    rev: v0.12.0
    hooks:
      - id: <one of the below>
      - id: <...any number of others>

  block-private-terms  Block a commit adding one of your own private terms.
  commitizen-early     Reject a bad commit message before the slow hooks run.
  embed-command        Keep a command's output (`--help`) true in the README.
  embed-tree           Regenerate the README file tree, and re-stage it.
  eslint               Lint with the project's own eslint, re-staging fixes.
  mypy                 Type-check the project in its own environment.
  pytest               Run the repo's tests through its own environment.
  regen-file           Run a generator script, and re-stage what it rewrote.
  ruff-check           Lint with `ruff check --fix`, re-staging what it fixed.
  ruff-format          Format with `ruff format`, re-staging what it rewrote.
  tsc                  Type-check the project with the project's own tsc.
  vitest               Run the project's vitest suite once, never in watch mode.
  zizmor               Audit GitHub Actions workflows for the mistakes that leak.

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
|   |-- workflows/
|   |   |-- ci.yml
|   |   `-- publish.yml
|   `-- zizmor.yml
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
|       |-- mypy_hook.py
|       |-- node_hooks.py
|       |-- pick.py
|       |-- privacy.py
|       |-- privacy_hook.py
|       |-- privacy_terms.py
|       |-- project_env.py
|       |-- pytest_hook.py
|       |-- regen_file.py
|       |-- restage.py
|       |-- ruff_hooks.py
|       |-- sync.py
|       |-- version.py
|       `-- zizmor_hook.py
|-- tests/
|   |-- test_audit.py
|   |-- test_cli.py
|   |-- test_commitizen_early.py
|   |-- test_doc_block.py
|   |-- test_embed_command.py
|   |-- test_embed_tree.py
|   |-- test_hook_docs.py
|   |-- test_hooks.py
|   |-- test_mypy_hook.py
|   |-- test_node_hooks.py
|   |-- test_packaging.py
|   |-- test_pick.py
|   |-- test_privacy.py
|   |-- test_privacy_hook.py
|   |-- test_privacy_terms.py
|   |-- test_project_env.py
|   |-- test_pytest_hook.py
|   |-- test_regen_file.py
|   |-- test_restage.py
|   |-- test_ruff_hooks.py
|   |-- test_sync.py
|   |-- test_version.py
|   `-- test_zizmor_hook.py
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
