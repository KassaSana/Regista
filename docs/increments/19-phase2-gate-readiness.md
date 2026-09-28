# Increment 19: Phase 2 gate readiness

Last updated: 2026-09-28

## Scope
Make the Phase 2 fan-value gate executable without full-match viewing, and address the known side-shift weaknesses. Add a second detector where the evidence required one. Freeze Phases 3–6. Everything ran on development data only.

## Changes
- **Side shift** ([research note 14](../research/14-side-shift-timing-and-wording.md)):
  - A team is evaluated only at its own final-third entries.
  - The sentence says a channel's share grew, and names a channel that still has more.
  - Possessives of names ending in "s" are fixed.
  - The golden snapshot was regenerated and reviewed; the independent recomputation was updated to match the new timing rule.
- **Domain and adapter:**
  - `ShotDetail` (penalty or not) on shot events.
  - The StatsBomb adapter maps shot types strictly and fails on unknown ones.
- **Attacking burst detector** ([research note 15](../research/15-second-detector-attacking-burst.md), [specification](../specs/phase-2-attacking-burst.md)):
  - unit, property-based prefix-invariance, golden, and independent-recomputation tests;
  - `regista replay` merges both detectors in replay order.
- **Research scripts:**
  - `phase2_side_shift_variants.py` and `phase2_attacking_burst.py`.
  - `phase2_judging_packet.py`, which writes the probe 02 packet.
  - Earlier audit scripts are pinned to the Phase 1 timing rule so notes 12, 13, and probe 01 still reproduce.
- **Documentation:**
  - A new gate and method ([probe 02](../research/probe-02.md)).
  - The roadmap Phase 2 section is condensed from a dated log into a plan, down from 34 KB to 18 KB.
  - [STATUS.md](../../STATUS.md) added; Phases 3–6 marked frozen.

## Verification
- **Checks:** 309 tests passed with no skips; Ruff lint and format passed; strict Pyright reported 0 errors.
- **Reproduction:** the variant study reproduced research notes 12 and 13 exactly under the Phase 1 rule (1,591 cards, 112 non-plurality, 316 other-team triggers, 100 of 446 sustained). A second full run was byte-identical.
- **Strict shot types:** all 800 development event files load with the stricter shot-type mapping.
- **Packet:** generation is deterministic (packet `be4eec07f144`). It was checked in a browser: 14 cards and 14 pitch maps rendered, and the answer export worked.
- **Isolation:** no validation or test match was opened.
