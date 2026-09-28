# Increment 15: Run provider contracts from the pinned corpus

Last updated: 2026-09-28

## Problem

Eight Phase 1 provider contracts still looked under the older
`data/statsbomb/` sparse checkout. This Windows checkout had the inspected
match in the verified `data/raw/` corpus, so those checks silently skipped
despite local evidence being available.

## Change

The Phase 1 replay, coordinate, and event contracts, plus the Phase 3
recorded-fact contract, now use one test-support function to resolve the
source commit from `catalog/corpus.toml` and find the inspected match under
`data/raw/`. Missing local provider data still causes a skip on clean CI.
No provider record is copied into the repository.

## Verification

All nine affected contract tests ran and passed against the pinned inspected
development match. The full suite reported 273 passed with no skips. Ruff lint
and format checks passed after formatting the touched files, and strict
Pyright reported zero errors.
