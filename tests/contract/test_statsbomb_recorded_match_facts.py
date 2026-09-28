"""Pin Phase 3 assumptions against an inspected development match only."""

from collections import Counter

import pytest
from pinned_events import pinned_events_path

from regista.adapters.statsbomb.events import load_events
from regista.detectors.recorded_match_facts import RecordedMatchFactsDetector
from regista.domain.ids import MatchId
from regista.domain.match_facts import FormationChangeFact, StartingLineupFact
from regista.domain.replay import replay

MATCH = MatchId(3773497)


@pytest.mark.contract
def test_inspected_match_records_two_starts_ten_substitutions_and_one_shape_change() -> None:
    path = pinned_events_path(MATCH)
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
