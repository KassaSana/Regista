# Increment 5: Provider catalog and frozen splits

Last updated: 2026-09-27

## Plan and scope

**Follow-up (2026-09-27):** the owner subsequently authorized starting acquisition while deferring the viewing probe. [Increment 6](06-reproducible-acquisition.md) records that superseding sequencing decision and the completed download. The execution record below describes the state at increment 5's completion.

Implement and run the metadata foundation of the [Phase 2 specification](../specs/phase-2-data-model.md). This increment reads competition and match indexes only. It does not open new event files or download lineups, tracking, or 360 frames. No scraping is needed: StatsBomb's versioned public repository provides the required indexes.

The full delivery plan is:

| Increment | Implementation and actual execution | Exit evidence |
|---|---|---|
| 5 — Catalog and frozen splits (current) | Record the 13 selected competition-seasons; fetch pinned index files; validate identity, dates, counts, and uniqueness; freeze development/validation/test assignments and 24 review identifiers. | Synthetic failure/boundary tests, real index coverage report, immutable split file, all repository checks. |
| 6 — Reproducible acquisition, after the probe decision | Standard-library HTTP adapter with timeout/retries, bounded download selection, immutable commit directories, append-only checksum manifest, restart/integrity checks, and explicit split routing. Start with the existing four development matches, then the authorized first wave. | Interrupted/repeated download tests; manifest verified against every acquired file; no 360 files. |
| 7 — Validation and normalized warehouse | Introduce the already-selected DuckDB runtime dependency only here; schema and transactional run ledger; original records retained; development and held-out files separated. Normalize the spine and fields earned by the probe. | Synthetic provider contracts and integrity checks; blocking failures excluded; reconcile sources, rows, goals, and exclusions. |
| 8 — Analytical tables and first-wave audit | Build versioned entries, score state, player intervals, time bins, and summaries as required by the surviving fan questions. Run Premier League development ingestion first; process held-out data only through mechanical validation, never exploratory queries. | Rebuild reproducibility, definition contracts, leakage checks, data-quality report, development-only research connection with external file access disabled. |
| Later Phase 2 waves | Add the remaining core leagues, then modern robustness only for a named research question. | Owner check-in after each wave; no default bulk collection of every available dataset. |

Each increment ends with a check-in, as required by AGENTS.md. The current request authorizes implementation and execution; it does not supply missing fan judgments. [Probe 01](../research/probe-01.md) remains owner-owned and pending. No production threshold or detector changes are part of this plan.

## Design choices for increment 5

- `catalog/corpus.toml` records provider identity, an exact source commit, selected identifiers, roles, coverage, expected counts, known gaps, and the already-inspected exceptions. It contains choices, not copied provider records.
- Provider parsing and HTTP requests stay inside the StatsBomb adapter. The domain carries only provider-neutral catalog types. The pipeline owns configuration, split calculation, and serialization. `cli.py` composes them.
- Raw indexes and metadata provenance snapshots stay under ignored `data/`. Each snapshot records the source URLs, checksums, byte counts, and retrieval times, and is keyed by the corpus configuration hash. That permits changed choices at the same provider commit without replacing old evidence. The future download manifest will import these provenance records; these snapshots are not the full ingestion manifest.
- Public `splits/v1.json` contains identifiers and choices only, plus source/configuration hashes and the generation rule. Raw index payloads, match scores, teams, and kickoff values stay local.
- Chronological boundaries minimize the total absolute distance from cumulative 70% and 85% targets over whole-date boundaries, requiring three nonempty date groups before exceptions. Ties choose the earlier boundaries. Too-small groups fail rather than silently losing a split.
- Already-inspected matches force their **entire competition-season date group** into development. This preserves the no-date-straddling invariant; any collateral promotions are recorded. The exception can interrupt chronological ordering, so reported fractions are descriptive rather than guaranteed 70/15/15.
- Six validation matches per core competition-season are selected by deterministic SHA-256 ranking with seed `20260927`. This avoids dependence on a Python random-generator implementation. Review identifiers are not labels or usefulness judgments.
- A versioned split is created exclusively and atomically. An existing version is never replaced, even by an equivalent run. Changes require a new version and a reason; version one records its initial creation reason.
- The first implementation supports the selected StatsBomb source through an adapter boundary. A generalized provider framework, live API credentials, scheduling, and additional providers are deferred until there is a concrete need.

## Execution record

Implemented `regista data catalog` and `regista data split` and ran both on 2026-09-27:

```console
uv run --no-sync regista data catalog
uv run --no-sync regista data split --reason "Initial Phase 2 split from pinned match indexes; already-inspected matches and their season-date groups assigned to development."
```

The catalog verified 14 index files totaling 3,488,070 bytes at provider commit `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`. They contain 1,894 matches across 13 competition-seasons: 1,517 core and 377 modern robustness. Metadata identifies 294 matches with 360 availability, but no frames were acquired. Both known missing-metadata records were detected, and the configured three-match Ligue 1 coverage gap is reported.

| Competition/season identifiers | Development | Validation | Test |
|---|---:|---:|---:|
| 2 / 27 | 266 | 57 | 57 |
| 11 / 27 | 277 | 54 | 49 |
| 12 / 27 | 268 | 55 | 57 |
| 7 / 27 | 264 | 55 | 58 |
| 9 / 281 | 24 | 5 | 5 |
| 7 / 108 | 18 | 4 | 4 |
| 7 / 235 | 22 | 5 | 5 |
| 11 / 90 | 25 | 5 | 5 |
| 43 / 106 | 46 | 10 | 8 |
| 55 / 43 | 36 | 8 | 7 |
| 55 / 282 | 36 | 8 | 7 |
| 223 / 282 | 22 | 5 | 5 |
| 1267 / 107 | 36 | 8 | 8 |
| **Total** | **1,340** | **279** | **275** |

`splits/v1.json` contains 24 validation review identifiers, six per core league. The four inspected matches and nine additional same-date matches are in development. Its SHA-256 is `4196a9df1a3f837698957a73b48d68e629869bb14339ab4c529d2ba819cf0ff3`.

An independent metadata audit checked unique membership, whole-date boundaries, chronological ordering outside recorded exceptions, inspected-match assignment, and review-set membership. Its local report is `out/catalog/validation.json`. A contract test reconstructs version one from verified local indexes; it skips when those indexes are absent. Unit tests and CLI tests use synthetic metadata only.

The [mechanical probe review](../research/03-probe-01-mechanical-review.md) reproduced all 45 existing observations and passed nine sampled prototype prefix checks. It recorded five pairs of observations within a minute and specific prototype implementation limitations. These are mechanical findings; owner judgments remain empty. Confidence in the recorded catalog counts and partition checks: **0.99**, based on exact input reconciliation and independent invariants, not a claim about the usefulness or representativeness of the corpus.

No project dependency was added, no new match event file was opened, and the detector was unchanged. The next increment remains reproducible acquisition after the probe decision and owner check-in; warehouse work has not started.

Final verification: `uv run pytest` passed all **115 tests**; `uv run ruff check .`, `uv run ruff format --check .` (57 files), and `uv run pyright` passed. `git diff --check` passed. Raw indexes and local audit output are ignored by Git. An independent read-only implementation review found no concrete correctness or leakage defects. The working tree already contained earlier Phase 1/2 work; no commit was made that could mix its ownership with this increment.
