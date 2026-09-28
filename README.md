# Regista

Last updated: 2026-09-28

Regista is a match companion for soccer fans. It replays a match in time order,
notices when something meaningful changes, explains it in one plain sentence,
and shows the evidence behind it.

Phase 1 is done: a StatsBomb adapter, a replay engine, and the attacking-side
shift detector turn a replayed match into cards with their supporting event
identifiers. Phase 2 has a pinned catalog of 1,894 matches, frozen
development/validation/test splits, 800 development matches in a local DuckDB
warehouse (no held-out match data), a second card type (attacking burst), and a
card-judging packet waiting on the owner's fan-value judgment. Current state:
[STATUS.md](STATUS.md). Plan: [ROADMAP.md](ROADMAP.md). Working rules:
[AGENTS.md](AGENTS.md). Specifications:
[attacking side](docs/specs/phase-1-attacking-side-shift.md),
[attacking burst](docs/specs/phase-2-attacking-burst.md), and the
[Phase 2 data model](docs/specs/phase-2-data-model.md).

## Development

Regista requires Python 3.13 and uses `uv` for its environment and lockfile.

```console
uv sync
uv run regista replay --match 3773497
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

`regista replay` reads the pinned corpus under
`data/raw/statsbomb-open-data/<source-commit>/data/events/<match>.json`
(override with `--events-dir`) and prints the side-shift and attacking-burst
cards in replay order, each with its time, sentence, and supporting event
identifiers. Add `--evidence` to see each side-shift card's channel table and
entries, and each burst card's shots, instead.

For the provisional Phase 3 recorded-fact stream, run
`uv run regista replay --match 3773497 --facts`. It shows starting shapes,
substitutions, and changed recorded formations separately from the default
card stream. Add `--evidence` to see the starting players and source
event identifiers. Fan usefulness and combined-stream attention cost are
still under review.

For the MVP viewer, `uv run regista export --match 3773497` writes
`out/exports/3773497.json` and refreshes `out/exports/index.json`. It accepts
development matches only and refuses any other match before reading a provider
file. The export follows `schemas/replay.schema.json` and is thin by design:
period boundaries, goals with the running score, cards with only their own
evidence events, and recorded facts, never the full event stream.

### Run the viewer

```console
uv run regista export --match 3773497
cd viewer
npm install
npm run dev
```

Open <http://localhost:5173>, pick a match, and play or scrub through it. The
viewer only reads exports from `out/exports` through its development server;
`npm run check` runs Biome, the TypeScript compiler, and Vitest.

Provider data belongs under `data/` and is intentionally excluded from version
control.

## Catalog and frozen splits

```console
uv run regista data catalog
```

This acquires only the competition and match indexes selected in
`catalog/corpus.toml`, pinned to an exact provider commit. Repeated runs verify
local checksums. It does not acquire event, lineup, or 360 files.

`splits/v1.json` is already frozen: 1,340 development matches, 279 validation,
275 test, and a 24-match validation review set. The generating command was:

```console
uv run regista data split --reason "Initial Phase 2 split from pinned match indexes; already-inspected matches and their season-date groups assigned to development."
```

Rerunning that command refuses to replace version one. A deliberate change
requires `--split-version 2` and a recorded reason. See the
[pipeline implementation plan](docs/increments/05-catalog-and-frozen-splits.md)
for the remaining acquisition, validation, and warehouse increments.

## Downloaded development data

Two development waves are downloaded: 800 matches (1,600 event and lineup
files plus 14 pinned indexes, about 2.3 GB) from 12 competition-seasons,
2015–2024. The first wave (266 Premier League 2015/16 matches plus four
already-inspected matches) is recorded in
[increment 6](docs/increments/06-reproducible-acquisition.md), and the second
(nine modern-robustness sets plus Serie A 2015/16) in
[increment 9](docs/increments/09-development-wave-2.md).

```console
uv run regista data download --competition 2 --season 27 --include-inspected
uv run regista data download --competition 2 --season 27 --include-inspected --verify-only
uv run regista replay --match 3753972
```

Completed downloads are verified and reused. The append-only manifest is
`data/raw/manifest.jsonl`; local reports are in `out/downloads/`. Explicit
held-out match identifiers are rejected. See [increment 6](docs/increments/06-reproducible-acquisition.md)
for restart behavior, provenance, and the completed execution record.

## Development warehouse

Validate the downloaded development matches and build the DuckDB warehouse
(development matches only):

```console
uv run regista data ingest --include-inspected --competition-season 2:27 --competition-season 12:27  # add each ingested C:S
uv run regista data quality
uv run regista data fingerprint --warehouse data/warehouse/regista.duckdb --compare <second build>
```

The build writes `data/warehouse/regista.duckdb` (never committed) atomically
and a data-quality report to `out/dq/`. Tables, definitions, and the corpus
inventory are described in
[increment 8](docs/increments/08-analytical-tables-and-first-wave-audit.md).
Open it for research with `regista.warehouse.research.connect_research`, which
is read-only and cannot read other files.

## Private backup and restore (Cloudflare R2)

Optional. Local `data/` stays the working copy; these commands only copy development
data to and from a private bucket, verifying SHA-256 checksums both ways. Copy
`.env.example` to `.env`, fill it in, then:

```console
uv run --env-file .env regista data remote push              # raw files + manifest (idempotent)
uv run --env-file .env regista data remote push --warehouse  # warehouse snapshot
uv run --env-file .env regista data remote verify --deep
uv run --env-file .env regista data remote pull --match 3773497              # just what a task needs
uv run --env-file .env regista data remote pull --warehouse latest --output data/warehouse/regista.duckdb
```

Held-out matches can never be pushed or pulled. See
[increment 10](docs/increments/10-remote-storage.md) and [DATA_SOURCES.md](DATA_SOURCES.md).

Contract tests (`tests/contract/`) read inspected match files from the pinned
`data/raw/` corpus and skip when those files are unavailable. Unit tests use
synthetic, hand-built events only.

## Data attribution

Regista is currently a non-commercial research and portfolio project.

Example match data used for research and analysis is sourced from
[StatsBomb Open Data](https://github.com/hudl/open-data) and is used subject to
the StatsBomb Public Data User Agreement.

Data: StatsBomb.

This repository does not redistribute StatsBomb raw data. To obtain the Open
Data, use StatsBomb's official repository. StatsBomb is the data source;
Regista's derived metrics, detectors, visualizations, and commentary are
produced by this project. Regista is an independent project and is not
affiliated with or endorsed by StatsBomb or Hudl. See
[DATA_SOURCES.md](DATA_SOURCES.md).

## Architecture

Application code uses a `src/` layout. The Phase 1 pipeline:

```text
load -> normalize -> replay -> detect -> render template -> card with evidence
```

| Stage | Module |
|---|---|
| Load and normalize | `regista.adapters.statsbomb.events` (the only code that knows StatsBomb's format) |
| Replay | `regista.domain.replay` |
| Detect | `regista.detectors.attacking_side_shift`, `regista.detectors.attacking_burst` |
| Render | `regista.templates` |

`regista.cli` is the composition root: the one module that chooses and wires
the concrete implementations. `tests/test_architecture.py` checks that the
domain, detectors, and templates never import adapters or third-party code.
