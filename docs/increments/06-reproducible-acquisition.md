# Increment 6: Reproducible development-data acquisition

Last updated: 2026-09-27

## Decision and scope

The owner explicitly requested starting data acquisition now after the research and catalog work. The [roadmap](../../ROADMAP.md) records this change in sequence: defer the viewing probe while acquiring the first development-data batch. No fan-usefulness judgment, license acceptance, or personal review was inferred.

This increment implements and runs acquisition for the 266 Premier League 2015/16 development matches plus the four already-inspected development matches. It fetches events and lineups from the pinned official repository. No scraping, API subscription, new provider, 360 frames, validation events, or test events are needed. The full corpus remains cataloged and split; additional acquisition waves require their own reason.

## Running it

```console
uv run regista data download --competition 2 --season 27 --include-inspected --dry-run
uv run regista data download --competition 2 --season 27 --include-inspected
uv run regista data download --competition 2 --season 27 --include-inspected --verify-only
```

Use `--match <identifier>` repeatedly for explicit development matches, or `--include-inspected` alone for the existing four. `--workers` defaults to four and is limited to eight. Explicit held-out identifiers are rejected before any match payload is fetched. Competition selection includes only its development members; it does not change or regenerate the split.

## Implementation

| File | Responsibility |
|---|---|
| `domain/acquisition.py` | Provider-neutral source-file requests and completion counts |
| `adapters/statsbomb/download.py` | Pinned URLs, events/lineups selection, bounded HTTP reads, transient retry policy, JSON-list validation |
| `pipeline/download.py` | Verify the split against the catalog, choose development matches, immutable file publication, append-only receipts, process locking, restart and integrity checks |
| `cli.py` | Compose the adapter and pipeline, show progress, write the local summary |

Raw bytes are stored under `data/raw/statsbomb-open-data/<source_commit>/data/`. Existing index receipts are imported into `data/raw/manifest.jsonl` after checksum verification, preserving their original retrieval times. Each match receipt records provider, dataset, exact commit, URL, raw-relative path, kind, match identifier, provider last-updated value, checksum, byte count, retrieval timestamp, license class, and the split checksum/bucket at first acquisition. Later use always revalidates the selected split; a historical receipt does not authorize a match for research under a different split.

An exclusive advisory process lock prevents two downloaders from appending simultaneously. A worker writes each raw file to a temporary file and publishes it atomically without replacement, syncing the file and directory entries. The main thread appends and flushes each completed receipt and syncs the manifest directory. Completed files survive failures; reruns check their bytes and skip network requests.

Missing manifested files are restored only if the pinned response matches the original checksum. An unmanifested file left after interruption is compared with a fresh pinned response before it receives a receipt. Conflicting bytes fail rather than being overwritten. A malformed or incomplete manifest fails closed and requires an audit; the tool never silently truncates or rewrites the evidence log.

HTTP reads have a thirty-second socket timeout and a 64 MiB per-file limit. Transient connection errors and HTTP 429/500/502/503/504 receive up to three retries with bounded delays. Permanent errors such as 404 fail immediately. This is finite source acquisition, not a live-feed client.

## Validation boundary

This increment verifies acquisition integrity and JSON container shape. It does not claim that every provider event already satisfies the normalized model. Full adapter validation, data-quality exclusions, goal reconciliation, and DuckDB ingestion are increment 7. Provider raw records remain local and unchanged; the project adds no runtime dependency here.

## Execution record

Completed on 2026-09-27 against source commit `b0bc9f22dd77c206ddedc1d742893b3bbe64baec` and the unchanged split SHA-256 `4196a9df1a3f837698957a73b48d68e629869bb14339ab4c529d2ba819cf0ff3`.

| Acquired input | Count |
|---|---:|
| Development matches | 270 |
| Event files | 270 |
| Event records | 931,293 |
| Lineup files | 270 |
| Competition and match indexes | 14 |
| Manifest receipts | 554 |
| Total bytes | 808,249,944 |
| Held-out match files | 0 |

First, the inspected-only run acquired eight match files and registered fourteen verified indexes. The first-wave run then acquired the remaining 532 files and verified the existing 22. A separate `--verify-only` pass verified all 554 files, made no downloads, and reported the same byte total. An independent audit recomputed checksums, parsed each JSON list, checked uniqueness and complete event/lineup pairs, and confirmed every acquired identifier belongs to the intended development selection before opening its payload.

The existing adapter and replay engine also processed Premier League development match `3753972`: 3,683 normalized events, with two side-shift cards. This is one smoke check; it is not a claim that all 270 files satisfy every downstream contract or that those cards are useful.

Local receipts and reports:

- `data/raw/manifest.jsonl`
- `out/downloads/inspected.json`
- `out/downloads/development-wave-1.json`
- `out/downloads/development-wave-1-verified.json`
- `out/downloads/development-wave-1-audit.json`

Validation: **128 tests passed**, including synthetic retries, resume, conflicting/orphan files, manifest truncation, missing-file restoration, concurrent-writer rejection, path escape rejection, unsupported split rules, held-out selection, and end-to-end CLI verification. Ruff lint, Ruff formatting (63 files), and strict Pyright passed. Independent review prompted additional split-metadata validation and directory syncing. First-acquisition split provenance remains immutable in receipts; current run reports record the split used for the current selection.

No frozen split, provider payload, detector threshold, runtime dependency, or license-confirmation checkbox was changed. Raw data and reports remain ignored by Git. The data acquisition increment is complete. Next: whole-corpus adapter validation and transactional normalization into the development DuckDB warehouse, with explicit exclusions and an ingest-run ledger.
