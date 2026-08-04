## v0.7.0 (2026-08-04)

### Feat

- add a pre-commit for eslint

## v0.6.0 (2026-08-03)

### Feat

- rename hook to embed-tree; bring over embed-command as well

### Fix

- debug ci and update claude
- remove git-release command I shan't be using
- pin version to readme

## v0.5.1 (2026-08-03)

### Fix

- don't install hooks when we pip install this package, they're distinct things

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
