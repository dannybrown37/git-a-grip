"""Run ruff out of this hook's own interpreter, and keep its fixes staged.

Same bargain as the commitizen hooks: ruff is a declared dependency of this
package, so `sys.executable -m ruff` resolves inside the env pre-commit built
here and a consuming repo needs no ruff on PATH, no venv, no `uv`. Pin a
different ruff per repo with `additional_dependencies: [ruff==x.y.z]`.

Both hooks rewrite files, and both re-stage what they rewrote -- including
`ruff check --fix`, whose fixes otherwise sit unstaged while the commit
records the unfixed code. A fixed file is committed as fixed; only the
violations ruff *could not* fix stop the commit, via ruff's own exit code.
"""

from __future__ import annotations

import subprocess
import sys

from git_a_grip import restage


def _ruff(*args: str) -> int:
    # Output is left to stream: ruff's diagnostics are the point of failing,
    # and pre-commit already buffers a hook's output until it finishes.
    return subprocess.run(  # noqa: S603
        [sys.executable, '-m', 'ruff', *args],
        check=False,
    ).returncode


def run(subcommand: str, args: list[str]) -> int:
    """Run a rewriting ruff subcommand over `args` and re-stage its edits."""
    paths = restage.target_paths(args)
    before = restage.digests(paths)
    # --force-exclude so the excludes in the repo's ruff config still apply
    # to the paths pre-commit passes explicitly.
    code = _ruff(subcommand, '--force-exclude', *args)
    fixed = restage.changed(before, restage.digests(paths))
    if fixed:
        sys.stderr.write(
            f'ruff {subcommand}: rewrote and re-staged {len(fixed)} file(s):\n'
            + ''.join(f'  {p}\n' for p in fixed),
        )
        if restage.add(fixed) != 0:
            sys.stderr.write('ruff: failed to re-stage the rewritten files.\n')
            return 1
    return code
