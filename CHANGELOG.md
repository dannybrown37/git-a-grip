## v0.5.0 (2026-08-03)

### Feat

- add hook-sync script; eslint/tsc hooks; readme tree script+hook

## v0.4.0 (2026-08-02)

### Feat

- prepare as a package for pypi, license, et al
- add pre-commit-audit command to help keep local repos in line

### Fix

- have CI handle releases after successful checks, max automation

## v0.3.1 (2026-08-02)

### Fix

- refuse to release on unrecognised arguments

## v0.3.0 (2026-08-02)

### Feat

- remove bump-on-push in favour of the git-release command
- git-release command that bumps before pushing

## v0.2.0 (2026-08-02)

### Feat

- update wording, relase python hooks

### Fix

- skip hooks on the bump commit so pre-push cannot re-enter itself

## v0.1.0 (2026-08-01)

### Feat

- commitizen-early and bump-on-push pre-commit hooks
