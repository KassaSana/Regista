# Phase 5 specification: Sourced context claims

Last updated: 2026-09-28

Status: infrastructure implemented with synthetic tests; no real claims or
context cards have been admitted.

## Purpose

A context card must show what a claim says, its original source, and when
Regista knew it. Claims are stored separately from the rebuildable development
warehouse in the git-ignored `data/context/claims.duckdb`. They are append-only
and use the same DuckDB engine. This store has no StatsBomb provider payloads.

## `source_claims` table

Each row has a unique claim identifier, a canonical subject identifier, a
predicate and string value, an optional validity interval, an original HTTPS
source URL, publication and retrieval timestamps, a store-recorded timestamp,
confidence, and license class. `valid_until` is exclusive. `published_at` may
be absent when the source's publication time is not known; such a claim can be
stored for research but cannot appear in an in-match context snapshot.

The claim identifier, subject, predicate, value, validity dates, published
timestamp, source URL, retrieved timestamp, confidence, and license class are
supplied by an authorized source workflow or the owner. The store sets
`recorded_at` from its own UTC clock and rejects attempts to supply or backdate
it. A duplicate identifier fails; historical rows are not edited. Confidence
is a claim assessment between zero and one, not a calibrated probability or a
license confirmation. No agent creates curated player or injury claims.

## Kickoff eligibility

The caller passes the relevant subjects, an explicit UTC kickoff instant, and
the match's local date. The store returns an immutable `KickoffContext` with
only claims for those subjects that satisfy all of these conditions:

1. `published_at` is known and strictly before kickoff.
2. `retrieved_at` and store-controlled `recorded_at` are at or before kickoff.
3. The local match date is within the validity interval.

The caller must not infer UTC kickoff from StatsBomb's local `match_date` and
`kickoff` fields, because the match metadata has no timezone. In-match updates
are outside this interface. A claim entered after a historical match cannot
be made eligible merely by assigning an earlier publication or retrieval date.

Snapshot claims retain the original URL, all three timestamps, validity, and
license class for the evidence view. A future card must link its specific
claim identifiers and source URLs; it must not use unsourced wording or infer
a medical condition from a substitution or return to play.

## Verification and remaining work

Synthetic tests cover publication, retrieval, and store-recorded cutoffs;
validity boundaries; missing publication time; subject isolation; immutable
snapshots; append-only identifiers; and UTC/URL validation. They contain no
real player facts. A Wikidata research adapter, owner-curated source records,
match timezone evidence, claim corrections, and context-card evaluation remain
future work. The Phase 5 gate is open.
