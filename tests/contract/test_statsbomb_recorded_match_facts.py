"""Pin Phase 3 assumptions against an inspected development match only."""

from collections import Counter
from pathlib import Path

import pytest

from regista.adapters.statsbomb.events import load_events
from regista.detectors.recorded_match_facts import RecordedMatchFactsDetector
from regista.domain.ids import MatchId
from regista.domain.match_facts import FormationChangeFact, StartingLineupFact
from regista.domain.replay import replay
from regista.pipeline.catalog import load_corpus

ROOT = Path(__file__).resolve().parents[2]
MATCH = MatchId(3773497)


@pytest.mark.contract
def test_inspected_match_records_two_starts_ten_substitutions_and_one_shape_change() -> None:
    source = load_corpus(ROOT / "catalog/corpus.toml").source_commit
    path = ROOT / "data/raw/statsbomb-open-data" / source / "data/events" / f"{MATCH}.json"
    if not path.exists():
        pytest.skip("inspected development match is not downloaded locally")

    events = load_events(path, MATCH)
    facts = list(replay(events, RecordedMatchFactsDetector()))
    assert Counter(type(fact).__name__ for fact in facts) == {
        "StartingLineupFact": 2,
        "SubstitutionFact": 10,
        "FormationChangeFact": 1,
    }
    event_ids = {event.identifier for event in events}
    assert all(fact.evidence_event_id in event_ids for fact in facts)
    assert all(len(fact.players) == 11 for fact in facts if isinstance(fact, StartingLineupFact))
    assert all(
        fact.previous_event_id in event_ids
        for fact in facts
        if isinstance(fact, FormationChangeFact)
    )
