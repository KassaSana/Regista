# Increment 7: Validation and the normalized development warehouse

Last updated: 2026-09-27

## Scope
The owner asked to begin Phase 2 data work: finish whatever the data foundation lacked, then reach the point where DuckDB can answer broad questions across a meaningful development corpus. Inspection showed the catalog, frozen splits, and acquisition were already done and verified (increments 5 and 6). This increment adds validation of every acquired development match and the normalized DuckDB layer. [Increment 8](08-analytical-tables-and-first-wave-audit.md) adds the analytical tables, data-quality reporting, the deterministic-rebuild check, and the inventory.

AGENTS.md asks for a check-in after each increment. The request explicitly covered both increments, so they ran back to back, and the check-in follows increment 8. Each record stands alone for review.

No provider, 360 frames, validation or test data, detector threshold, or license box was touched. Only the development warehouse is built; `held_out.duckdb` waits until evaluation needs it (no held-out raw files exist).

## Running it

```console
uv run regista data ingest --competition 2 --season 27 --include-inspected
uv run regista data quality          # rewrites out/dq/latest.md and latest.json
uv run regista data fingerprint --warehouse data/warehouse/regista.duckdb --compare <other build>
```

`ingest` accepts the same selection options as `download`. It revalidates the frozen split, verifies every raw file against its manifest receipt on the bytes it parses, rebuilds the whole warehouse into a temporary file, and replaces `data/warehouse/regista.duckdb` atomically. A failed run leaves the previous warehouse untouched, and it cannot disturb a reader, such as the read-only DuckDB server, that holds the old file open. A full rebuild of 270 matches takes about 45 seconds, so rebuilding from immutable raw files is the restart strategy. There is no per-match resume state.

## Design

| Location | Responsibility |
|---|---|
| `domain/matches.py`, `domain/lineups.py`, `domain/normalized.py` | Provider-neutral match, lineup, and row records; `FIELD_AVAILABILITY` tags every normalized column `known_at_event`, `delayed`, or `hindsight` |
| `domain/events.py` | `ActionType` grew additively to the 17 Regista event types. The detector reads only ball movements, so the golden snapshot is unchanged. |
| `adapters/statsbomb/events.py` | Every StatsBomb type (open-data v4) mapped; **an unknown type now fails loudly** |
| `adapters/statsbomb/matches.py`, `lineups.py`, `normalize.py` | Match index records, lineups (continuous `MM:SS` clock → period seconds, offsets 0/45/90/105/120), and whole-match normalization, including derived goals |
| `pipeline/ingest.py` | Checksum verification, the adapter call, blocking rows for failures, and the `WarehouseWriter` port. Refuses any match not acquired as development. |
| `warehouse/` | The only package importing `duckdb` (enforced by the architecture test): schema SQL, quality SQL, analytical SQL, builder, and research connection |
| `cli.py` | Composition root: the `ingest`, `quality`, and `fingerprint` commands, plus the run identity |

Decisions:
- **Staging.** Rows are staged as newline-delimited JSON and loaded with `read_json` using column types read from the created schema, so types are declared once, in SQL. This needs no pandas or pyarrow. The only new dependency is `duckdb` (1.5.5), already decided in `docs/STACK.md`.
- **Run identity.** `ingest_run_id` is a hash of the Regista version, git commit, dirty flag, a digest of the package source (including SQL), the adapter version, the source commit, the split checksum, and every selected raw file checksum. Identical inputs and code give the same ID; wall-clock times live only in `ingest_runs`.
- **Original records.** `events`, `appearances`, and `matches` keep the provider record as a `JSON` column.
- **Goals.** A shot with outcome Goal, or an "Own Goal For" event credited to that event's team. Shootout goals (period 5) are flagged, and excluded from score states and reconciliation.
- **Failures.** A match that fails checksum or adapter validation keeps its metadata row, gets `dq_status = 'excluded'`, and is listed. It is never silently dropped.
- **Research connection.** Read-only, with `enable_external_access = false`, which cannot be re-enabled on an open connection. A test proves it cannot read an outside file.

## Normalized tables (`normalized` schema)
`ingest_runs`, `raw_files`, `splits`, `competition_seasons`, `matches`, `teams`, `players`, `appearances`, `position_spells`, `events`, `passes`, `carries`, `shots`, `substitutions`, `formation_changes`, `goals`, `field_availability`, `dq_checks`. Every row carries `ingest_run_id`. Columns and counts are in the [increment 8 inventory](08-analytical-tables-and-first-wave-audit.md#inventory).

## Problems found and fixed during this increment
- DuckDB's `format()` returns NULL for a NULL argument, which violated `dq_checks.detail NOT NULL` on missing metadata. The arguments are now coalesced, and a firing test covers it.
- The run ID originally ignored uncommitted code changes. It now includes a source digest.

## Validation
- 270 of 270 development matches passed adapter validation and every blocking check.
- Contract tests pin the period offsets, the own-goal credit, development-only contents, and SQL/domain entry parity on match 3773497 (126 entries, matching the Phase 1 record).
- Repository checks at the end of increment 8: 220 tests passed (205 synthetic and unit, 15 contract against local data), Ruff lint and format passed, and strict Pyright reported 0 errors.
