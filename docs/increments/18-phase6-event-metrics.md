# Increment 18: Phase 6 event-data metrics

Last updated: 2026-09-28

## Scope

Define recovery location and completed-movement directness on development
events and run the definitions across all 800 local development matches. This
is retrospective research, not an in-match detector or a defensive-line
estimate. See [research note 11](../research/11-event-data-recovery-and-directness.md).

## Verification

The read-only script covered all 1,600 team-matches, with no invalid selected
coordinates. The full suite reported 283 passed with no skips; Ruff lint and
format checks passed and strict Pyright reported zero errors. No held-out
match was opened.
