# Increment 16: Point-in-time source-claim store

Last updated: 2026-09-28

## Scope

Create a separate append-only DuckDB `source_claims` table and a
provider-neutral claim type. `freeze_at_kickoff` requires an explicit UTC
kickoff and local match date. It admits only claims published, retrieved, and
recorded by the store before kickoff and valid on the match date. Unknown
publication time is a hard exclusion. See the [Phase 5 specification](../specs/phase-5-source-claims.md).

No real-world claim is added, and no fan-facing context card is emitted. The
source-claim database lives under git-ignored `data/context/`, separate from
the reproducibly rebuilt provider warehouse.

## Verification

Five synthetic tests pass for the time, source, subject, immutability, and
append-only contracts. The full suite reported 278 passed with no skips.
Ruff lint and format checks passed after formatting the touched identifier
file, and strict Pyright reported zero errors.
