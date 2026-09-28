# Increment 14: Action-value research foundation

Last updated: 2026-09-28

## Scope

Add a provider-neutral `ActionValuer` contract and two implementations for
completed open-play passes and carries: a geometric heuristic and a 16-by-12
expected-threat surface. The grid trainer reads development data only and
writes a git-ignored research artifact with provenance. A strict date cutoff
can generate a surface using earlier matches only. It is not yet a card
detector or player rating.

## Verification

Synthetic tests cover the two-cell expected-threat equation, failed moves in
the denominator, invalid counts, unsupported actions, and replay prefix
invariance. The matched synthetic equations were cross-checked with
socceraction in a throwaway Python 3.12 environment. The development trainer
converged from 800 matches in 85 iterations. See [research note 08](../research/08-expected-threat-foundation.md)
for definitions, counts, exclusions, uncertainty, and the chronological
evaluation requirement.

The full suite reported 263 passed and 8 skipped. Ruff lint and format checks
passed, and strict Pyright reported zero errors. The skipped contracts require
the older sparse-checkout data location; the development-only trainer was run
against the manifest-backed warehouse separately.
