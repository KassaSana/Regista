"""The replayed score of the inspected match ends at the provider's recorded final score.

Reads the locally downloaded event file and match index; skips when they are missing.
The recorded final score is hindsight, so only this test reads it, never a detector.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pinned_events import pinned_events_path

from regista.adapters.statsbomb.catalog import load_catalog
from regista.adapters.statsbomb.events import load_events
from regista.adapters.statsbomb.matches import load_match_records
from regista.domain.ids import MatchId
from regista.domain.score import Score, ScoreTracker
from regista.pipeline.catalog import load_corpus

pytestmark = pytest.mark.contract

MATCH_ID = MatchId(3_773_497)
ROOT = Path(__file__).resolve().parents[2]
RAW_DIRECTORY = ROOT / "data/raw"


def test_replayed_score_ends_at_the_recorded_final_score() -> None:
    events_path = pinned_events_path(MATCH_ID)
    if not events_path.exists():
        pytest.skip(f"download StatsBomb match {MATCH_ID} to run the score contract")
    configuration = load_corpus(ROOT / "catalog/corpus.toml")
    catalog = load_catalog(configuration, RAW_DIRECTORY)
    record = load_match_records(configuration, catalog, RAW_DIRECTORY, [MATCH_ID])[MATCH_ID]
    tracker = ScoreTracker(record.home_team.identifier, record.away_team.identifier)

    scores = [tracker.observe(event) for event in load_events(events_path, MATCH_ID)]

    assert scores[-1] == Score(record.home_score, record.away_score)
    # The score never goes down and changes by at most one goal per event.
    for before, after in zip([Score(0, 0), *scores], scores, strict=False):
        assert (after.home - before.home, after.away - before.away) in {(0, 0), (1, 0), (0, 1)}
