# Increment 10: Private R2 backup and restore

Last updated: 2026-09-27

## Scope
The 800-match development corpus (2.3 GB raw, 1.5 GB warehouse) needs a durable copy off this machine, so local disk can be freed later without losing reproducibility. The intended sequence is:

1. 800-match dataset verified.
2. R2 backup and cache.
3. Prove a restore.
4. Free disk space.
5. Phase 2 research.

This increment implements and tests step 2 locally. **No real upload has been made.** The StatsBomb private-storage decision in [DATA_SOURCES.md](../../DATA_SOURCES.md) is still unchecked, and it is the owner's to make.

Local paths remain the working copy. `download`, `ingest`, `replay`, and `fingerprint` are unchanged and never talk to R2. The new `regista data remote` commands only move data between `data/` and a private bucket.

## Design

| Location | Responsibility |
|---|---|
| `pipeline/remote.py` | Cloud-neutral orchestration behind an `ObjectStore` protocol (`stat`, `upload`, `download`, `put_bytes`, `get_bytes`, `keys`, and deliberately no delete); push, verify, pull, warehouse snapshots, and every leakage guard |
| `storage/r2.py` | The only module importing `boto3` (enforced by the architecture test). It reads credentials from environment variables only. |
| `warehouse/research.py` | `snapshot_facts`: the ingest run, the count of non-development matches, and the fingerprint |
| `adapters/statsbomb/catalog.py` | `provenance_relative_path`: where the corpus's metadata provenance receipt lives |
| `cli.py` | `regista data remote push \| verify \| pull` |

### Bucket layout
```
raw/statsbomb-open-data/<commit>/data/...                 same path as data/raw; never overwritten
raw/statsbomb-open-data/<commit>/metadata-provenance/<corpus-sha>.json
manifests/manifest-<sha256>.jsonl                          immutable manifest snapshots
manifests/latest.json                                      pointer; moves only forward
warehouse/<ingest_run_id>/regista.duckdb, dq.md, dq.json, snapshot.json
warehouse/latest.json
reports/downloads/<name>-<sha12>.json                     acquisition summaries
```
- Every object stores its SHA-256 in object metadata.
- An existing object with different contents is a hard failure.
- The manifest pointer moves only when the remote manifest is a prefix of the local one, matching the local append-only rule.
- `snapshot.json` is written last, so its presence means the snapshot is complete. It records the ingest run (run ID, git commit and dirty flag, source commit, split version and SHA, selection, and versions), the manifest snapshot SHA, the corpus configuration SHA, the split-file SHA, the file SHA and bytes, and the full table fingerprint.
- A snapshot is identified by run ID and fingerprint rather than file bytes, because DuckDB files need not be byte-identical across equivalent builds.

### Leakage guards
- `push` refuses the whole upload if any manifest match receipt is not development under the current split, before transferring anything.
- `pull` checks explicitly named matches against `splits/v1.json` **before reading credentials or touching the network**. Every other selection goes through `select_development_matches`, which revalidates the frozen split against the catalog. There is no "download everything" or arbitrary-key mode.
- `verify` audits the bucket: any raw object that is neither a development receipt nor a metadata file is reported.
- `push --warehouse` refuses a warehouse holding any non-development match. It also refuses a build from uncommitted code unless `--allow-dirty` is given, because such a build cannot be reproduced from git.
- Held-out data never goes to this bucket. If evaluation ever needs held-out files remotely, they get a separate bucket and token, as a separate decision.

### Credentials
The four variables are `REGISTA_R2_ACCOUNT_ID`, `REGISTA_R2_ACCESS_KEY_ID`, `REGISTA_R2_SECRET_ACCESS_KEY`, and `REGISTA_R2_BUCKET`.
- They go in `.env`, which is git-ignored and copied from the committed `.env.example`, and are used through `uv run --env-file .env`.
- A missing variable produces an error naming the variable, never any value.
- The boto3 client uses R2's endpoint with `region_name="auto"`, standard retries, and S3 checksum headers only where required. Regista verifies SHA-256 itself on every transfer.

## Dependencies
- Runtime: `boto3` (1.43.103), confined to `regista.storage`.
- Development: `boto3-stubs[s3]` for strict Pyright.

This is recorded in [docs/STACK.md](../STACK.md).

## Evidence

**Tests.** 248 passed (233 synthetic and unit, 15 contract); Ruff lint and format clean; strict Pyright reports 0 errors. The new tests use a directory-backed fake store and botocore's Stubber, so there is no network:
- push uploads with checksum metadata, and a second push uploads nothing;
- a held-out receipt, a tampered local file, a conflicting remote object, or a sideways manifest pointer each stops the push before any transfer;
- verify detects a missing object, a wrong size, corrupted contents (deep), and stray objects;
- pull restores exact bytes, only the selected matches, skipping present files; it refuses held-out matches with zero transfers, rejects corrupted remote bytes without publishing them, keeps a local manifest that is ahead, and rejects a divergent one;
- warehouse snapshots round-trip; unsafe or dirty snapshots are refused; a fingerprint conflict fails; a restore that fails its fingerprint leaves no file behind; a real synthetic DuckDB warehouse restores with an equal fingerprint;
- the R2 adapter handles missing credentials (names only, the secret never shown), the endpoint, 404 versus other errors, and put, get, and list;
- the CLI refuses a held-out `--match` before reading credentials;
- the architecture test confirms only `regista.storage` imports boto3.

**Local rehearsal on the real 800-match corpus**, with a local directory standing in for R2 (scratch data deleted afterwards; canonical data only read):

| Step | Result |
|---|---|
| Push | 1,615 objects (1,614 manifest files plus provenance), 2,443,928,939 bytes, plus manifest snapshot `f1076a4f4245` |
| Second push | 0 uploaded, 1,615 unchanged |
| Deep verify | 1,615 checked, 0 problems |
| Restore into an empty directory | Manifest, 15 metadata files, and 1,600 match files for 800 matches |
| `data download --verify-only` on the restored directory | 1,614 verified, 0 downloaded |
| Warehouse from original files vs from restored files (same code) | `fingerprint --compare`: **Identical** (run `2a2ca65459d76e2e`) |
| Warehouse snapshot push, then pull | Dirty build refused without `--allow-dirty`; with it, 1.6 GB stored and restored; fingerprint equal to the original build |
| Held-out match pull | Refused, 0 transfers |

## Reproducibility note
`ingest_run_id` includes a digest of the package source, so any code change (including this increment) gives new builds a new run ID.

The canonical `data/warehouse/regista.duckdb` was built before this increment (run `9a6c9d48abd4fa3f`, dirty tree). For a snapshot that is reproducible from git:
1. Commit.
2. Rebuild with `ingest`.
3. Run `remote push --warehouse`.

Rebuilding replaces the warehouse file atomically from the same immutable raw files; it deletes no raw data.

## Remaining (owner)
1. Decide and record the private-storage question in `DATA_SOURCES.md`.
2. Do the Cloudflare setup and create `.env`.
3. Run the first real upload, deep verification, and restore proof.
4. Only then free local disk space.

## Addendum (2026-09-27): state after the first commits
- The increment's code is committed (`41db472`), so step 1 of the reproducibility note is done.
- The canonical warehouse has **not** been rebuilt. It is still run `9a6c9d48abd4fa3f` (git commit `449aa78`, dirty tree), with 800 development matches and 0 non-development matches, checked read-only on this date.
- No real upload, `.env`, or bucket exists. The owner items above are unchanged.

## Addendum (2026-09-27): owner decision recorded; real proof blocked on setup
- Kassahun recorded the private-storage decision and his reading of the agreement in `DATA_SOURCES.md` (owner item 1 above is done).
- The real restore proof was not started. There is no `.env` in the repository root and no `REGISTA_R2_*` variable in the environment. Without them, `storage/r2.py` cannot reach a bucket, and working around that is out of scope.
- Minimum owner action:
  1. Create a private R2 bucket (no `r2.dev` URL, no custom domain) and an API token with object read and write on that bucket only.
  2. Copy `.env.example` to `.env` and fill in the four values.
- Free disk space on this date was about 17 GiB. A full scratch restore needs about 4 GB (2.3 GB raw plus a 1.5 GB warehouse), and a second scratch warehouse about 1.5 GB more.
