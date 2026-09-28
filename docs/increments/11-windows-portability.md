# Increment 11: Windows development and acquisition portability

Last updated: 2026-09-28

## Reason

The first full check on a Windows checkout could not collect tests because the
acquisition pipeline imported Unix-only `fcntl`. After that import was fixed,
tests exposed two more Windows file-handling differences: `os.open` cannot open
a directory for `fsync`, and `os.fsync` rejects a read-only file descriptor.
These were portability defects in existing Phase 2 acquisition and restore code.

## Changes

- Acquisition still holds one non-blocking lock while it reads the manifest and
  appends receipts. On Windows it locks one byte of `.acquisition.lock` with
  `msvcrt`; on Unix it continues to use `fcntl.flock`. The lock is released on
  normal and exceptional exits. The concurrent-writer test exercises the same
  public lock on both platforms.
- File contents are still flushed and synced before publication. Directory
  `fsync` runs on Unix. Windows has no directory descriptor through Python's
  `os.open`, so that step is skipped there. Resume and verification still check
  each file against its immutable manifest receipt. This does not claim the same
  crash-durability guarantee for directory entries on Windows as on Unix.
- The remote manifest restore opens its temporary file for writing before
  `fsync`, as required on Windows.

## Verification

On Windows with Python 3.13.15 and the locked environment:

- `uv run pytest -q`: 233 passed, 15 skipped. The skipped contract tests require
  local StatsBomb data, which is absent in this checkout.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed after formatting.
- `uv run pyright`: 0 errors.

The checkout has no local corpus or R2 credentials, so this increment does not
repeat the real corpus or remote restore proof recorded in increment 10. It
changes no detector definition, split, or research conclusion.
