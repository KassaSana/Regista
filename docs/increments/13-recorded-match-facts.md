# Increment 13: Provisional recorded match facts

Last updated: 2026-09-28

## Reason and scope

Phase 3 asks for facts from starting lineups, substitutions, and recorded
formation changes. [Research note 07](../research/07-recorded-match-facts.md)
found that most `Tactical Shift` events repeat the previous formation and that
showing every candidate would add roughly ten facts per match. This increment
implements a separate stream for correctness and later evaluation, without
promoting it into the default card feed.

## Changes

- The StatsBomb adapter extracts named players and formations into typed domain
  event details. It validates that a starting event has eleven distinct players.
- The recorded-fact detector emits starting-lineup and substitution facts, and
  emits a formation-change fact only when the shape differs from the team's
  previous recorded shape. It keeps previous and current evidence identifiers
  and source names. It never uses provider reasons for injury or tactical intent.
- The ordered replay iterator now accepts different insight types, so both
  detectors retain the same prefix-order check.
- `regista replay --facts` displays candidate facts separately; `--evidence`
  displays the source events and starting-player names. The ordinary replay
  output is unchanged.

## Verification

Synthetic adapter and detector tests cover firing, quiet, suppression, team
isolation, evidence, and prefix invariance. A read-only replay of all 800
development event files completed without a parsing or ordering failure and
produced exactly the inventory's expected counts: 1,600 starting lineups,
5,384 substitutions, and 743 changed formations. This validates the mechanical
translation on the development corpus; no held-out match file was opened.
An inspected-development-match contract test pins the provider fields and
counts (two starting lineups, ten substitutions, one changed formation).
The full suite reported 253 passed and 8 skipped; Ruff lint and format and
strict Pyright passed.

The owner probe and combined-stream attention and redundancy judgments remain
pending. The Phase 3 gate is not marked complete.
