"""Locate a pinned provider event file without fetching or copying it."""

from pathlib import Path

from regista.pipeline.catalog import load_corpus

ROOT = Path(__file__).resolve().parents[2]


def pinned_events_path(match_id: int) -> Path:
    source = load_corpus(ROOT / "catalog/corpus.toml").source_commit
    return ROOT / "data/raw/statsbomb-open-data" / source / "data/events" / f"{match_id}.json"
