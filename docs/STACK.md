# Regista Technology Stack

Last updated: 2026-09-28

This is the record of which languages, tools, and approaches Regista uses, when each one arrives, and why. Changing a choice here is a recorded decision (see [AGENTS.md](../AGENTS.md)).

## Principles
- **Two languages, split along one line.**
  - **Python** computes everything: loading, normalization, replay, detectors, templates, models.
  - **TypeScript** only displays results.
- **One contract between them.** Python exports a versioned JSON file per match (the replay export), described by a JSON Schema. The viewer never reads provider data and never decides anything ("detectors decide; templates render").
- **Dependencies arrive with the phase that needs them.** Nothing is installed early. Domain code stays standard-library only.

## Stack by layer

| Layer | Choice | Arrives | Why |
|---|---|---|---|
| Engine language | Python 3.13 | Now | The data and machine-learning ecosystem |
| Environment and packaging | uv | Now | Pins Python and the lockfile |
| Lint and format (Python) | Ruff, plus an edit hook for agents | Now | One fast tool |
| Types (Python) | Pyright, strict mode | Now | Protocols and domain types carry the design |
| Tests | pytest + Hypothesis | Now | Examples plus property tests (for example, prefix invariance) |
| Domain model | Standard-library frozen dataclasses, enums, `NewType` identifiers, `Protocol` ports | Phase 1 | No third-party imports in the domain |
| Provider parsing | Standard-library `json` + `TypedDict`, validated by hand in the adapter | Phase 1 | Only a few fields; Pydantic only if parsing grows |
| Replay engine | A plain Python iterator ordered by provider `index` (`domain/replay.py`). Each detector is an incremental object that observes one event at a time and returns cards. | Phase 1 | Prefix invariance holds by construction, and the same code can later run live |
| Command-line interface | argparse in `cli.py`, the composition root | Now / Phase 1 | Already in place; `regista replay --match <identifier>` |
| Data download | Standard-library `urllib`, pinned to a provider commit, writing into `data/raw/` with a checksummed manifest (`regista data download`) | Phase 2 | No HTTP dependency needed; reproducible inputs |
| Warehouse and exploration | DuckDB holding the normalized and analytical tables: `data/warehouse/regista.duckdb` for development matches (the only file research tools, including the read-only DuckDB server for agents, open) and `data/warehouse/held_out.duckdb` for validation and test. The `duckdb` Python package is a **runtime** dependency confined to `regista.warehouse`; the architecture test enforces that nothing else imports it. It arrived with ingestion wave 1 (`duckdb` 1.5.5, increment 7). (Decision 2026-09-27: it was a development dependency, but building the tables is part of the pipeline, not only exploration.) | Phase 2 | SQL over thousands of matches without running a database server |
| Remote durable storage | A private Cloudflare R2 bucket through its S3-compatible API with `boto3` (runtime dependency, confined to `regista.storage`; `boto3-stubs[s3]` for type checking). Local `data/` stays the working copy; `regista data remote push \| verify \| pull` sync it. Credentials come from environment variables in git-ignored `.env`. (Decision 2026-09-27: lets the corpus leave the local disk without changing any local workflow; no database service or daemon.) | Phase 2 | Durable, restorable copy of pinned raw files and warehouse snapshots; egress-free restores |
| Replay export | One JSON file per match, written by `regista export` (development matches only) and described by `schemas/replay.schema.json` (version 1, added 2026-09-28). Thin by design: period boundaries, goals with the running score, cards with only their own evidence events and locations, and recorded facts; never the full event stream (DATA_SOURCES.md). Tests validate it with `jsonschema` and `types-jsonschema`, development dependencies only. | MVP M2 | The contract between Python and TypeScript |
| Viewer | TypeScript (strict, `noUncheckedIndexedAccess`) + Vite + React in `viewer/`; no router, state library, or UI kit. A development-only Vite plugin serves `out/exports` at `/exports`; a build never copies an export. (Arrived with MVP M3, 2026-09-28: Vite 8, React 19, TypeScript 6. The template's oxlint was replaced by Biome, as recorded below.) | MVP M3 | Chosen for learning and portfolio value; React is the most widely used |
| Pitch drawing in the viewer | Hand-written SVG components, no d3 (`viewer/src/Pitch.tsx`, arrived with MVP M4: the acting team's attacking frame, final-third and channel guides, evidence only) | MVP M4 | A pitch is rectangles and arcs; a good learning exercise |
| Viewer types | Generated from the JSON Schema (`json-schema-to-typescript`, `npm run types`) into the committed `viewer/src/replayTypes.ts` | MVP M3 | One source of truth for the contract |
| Viewer lint, format, tests | Biome + Vitest (`npm run check` also runs `tsc`); tests use synthetic exports only | MVP M3 | Biome is the TypeScript counterpart of Ruff |
| Browser checks | Playwright | Phase 2 | Screenshots and one end-to-end test |
| Static figures for write-ups | mplsoccer + matplotlib | Phase 2 | Pitch maps carrying the StatsBomb logo |
| Continuous integration | GitHub Actions (`.github/workflows/ci.yml`): Python 3.13 from `.python-version`, `uv sync --locked`, Ruff lint and format check, strict Pyright, pytest. Contract tests skip because provider data is never in the repository; no secrets, corpus download, or deployment. The viewer build and tests join when the viewer exists. | Phase 2 (2026-09-27, with the private GitHub backup) | Every push is checked on a clean machine with synthetic data only |
| Modeling | NumPy 2.5.3 for our own expected-threat implementation (added 2026-09-28); scikit-learn `HistGradientBoostingClassifier` for a later possession-value experiment. `socceraction` only in a throwaway Python 3.12 environment for cross-checks. | Phase 4 | Learning first; no Python downgrade |
| Context store | An append-only `source_claims` table in a separate git-ignored DuckDB file at `data/context/claims.duckdb` (added 2026-09-28); Wikidata through SPARQL over `urllib` later | Phase 5 | Same engine as exploration, while claims survive development-warehouse rebuilds |
| Tracking and 360 data | kloppy, inside an adapter only | Phase 6 | Standard loaders for SkillCorner and StatsBomb 360 |

## Explicitly not using
- pandas in the domain.
- Spring Boot, Java, or PostgreSQL. DuckDB covers storage at this scale.
- Streamlit.
- A language model in the product. It remains an optional branch in the roadmap.
- statsbombpy: not needed, and its license is unclear.
- A Python downgrade.

## Repository layout (target by Phase 2)
```
src/regista/        Python engine (domain/, adapters/, detectors/, templates.py, cli.py)
tests/              unit/ (synthetic fixtures), contract/ (local provider data, skipped when absent), golden/ (derived snapshots)
schemas/            replay.schema.json (the Python ↔ TypeScript contract)
viewer/             TypeScript + React + Vite app that reads exported JSON
catalog/            corpus.toml: which competition-seasons Regista uses, and in which role
splits/             v<N>.json: frozen development/validation/test assignments (identifiers only)
scripts/            plotting scripts
data/               git-ignored: raw/ (pinned provider files and manifest), warehouse/ (DuckDB)
out/                git-ignored: generated exports and data-quality reports
```

## Prerequisites and constraints
- Node 26.5.1 is installed (checked 2026-09-28), which is recent enough for current Vite. The viewer arrived with MVP M3 ([increment 20](increments/20-mvp-plan.md)).
- A public demo of the viewer follows [DATA_SOURCES.md](../DATA_SOURCES.md): it publishes derived insights and aggregates with a limited set of evidence per card, never raw provider files or a near-complete event export, and every card or image carries "Data: StatsBomb" and the official logo.
