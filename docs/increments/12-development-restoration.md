# Increment 12: Restore the development warehouse on Windows

Last updated: 2026-09-28

## Scope

Restore the same frozen 800 development matches from the pinned StatsBomb Open
Data commit in a Windows checkout. This is a local working copy of the existing
corpus, not a new wave or a change to `splits/v1.json`. No validation or test
event or lineup file was selected.

## Execution

- `regista data catalog` verified 1,894 match indexes across 13 seasons.
- `regista data download --include-inspected` restored the four previously
  inspected development matches. The probe generator reproduced its recorded
  per-kind observation counts from these files.
- `regista data download` with the 11 development competition-seasons listed in
  increment 9 selected 800 matches and 1,614 source files. It acquired 1,592
  match files and verified 22 already present. A separate `--verify-only` pass
  checked all 1,614 files (2,443,923,640 bytes), with zero downloads.
- `regista data ingest` normalized 800 of 800 matches, with zero adapter or
  checksum failures. Run `72e2ced0e72fc4eb` was built from clean commit
  `1aa2425a66cf` and split version one.

## Verification

The development warehouse has 32 normalized and analytical tables and zero
matches outside the development split. Its quality report has 647 matches
passing all checks and 153 passing with warnings; all seven blocking checks pass
for all 800 matches. Warning counts match the earlier corpus record: 128 clock,
3 coordinate, 12 position-spell, 1 metadata, and 21 substitution-end warnings.

On this checkout: `uv run pytest -q` reported 241 passed and 8 skipped;
Ruff lint and format checks passed; strict Pyright reported zero errors.
The remaining skipped contract tests expect the older `data/statsbomb/` sparse
checkout rather than the manifest-backed `data/raw/` files. The raw files,
warehouse, reports, and probe sheets remain git-ignored.

## Next step

Research can now use the full development warehouse. The owner viewing probe
and its fan-usefulness decision remain pending. No detector threshold or
product gate is changed by this restoration.
