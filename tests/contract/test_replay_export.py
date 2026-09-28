"""The replay export of the inspected match agrees with the goldens and the recorded result.

Reads the locally downloaded event file and match index; skips when they are missing.
No export is written or committed: the check runs in memory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from pinned_events import pinned_events_path
from replay_schema import validate_export

from regista.adapters.statsbomb.catalog import load_catalog
from regista.adapters.statsbomb.events import load_events
from regista.adapters.statsbomb.matches import load_match_records
from regista.domain.ids import MatchId
from regista.pipeline.catalog import load_corpus
from regista.product import build_match_export

pytestmark = pytest.mark.contract

MATCH_ID = MatchId(3_773_497)
ROOT = Path(__file__).resolve().parents[2]
RAW_DIRECTORY = ROOT / "data/raw"
GOLDEN_KINDS = {"attacking-side-shift": "side_shift", "attacking-burst": "burst"}

type Json = dict[str, object]


def _golden_cards() -> list[tuple[str, str, Json]]:
    cards: list[tuple[str, str, Json]] = []
    for name, kind in GOLDEN_KINDS.items():
        golden = json.loads((ROOT / "tests/golden" / f"{MATCH_ID}-{name}.json").read_text())
        for card in cast(list[Json], golden["cards"]):
            clock = {key: card[key] for key in ("period", "minute", "second")}
            cards.append((f"{kind}-{card['trigger_event_id']}", str(card["sentence"]), clock))
    return sorted(cards)


def test_export_matches_the_goldens_and_ends_at_the_recorded_score() -> None:
    events_path = pinned_events_path(MATCH_ID)
    if not events_path.exists():
        pytest.skip(f"download StatsBomb match {MATCH_ID} to run the export contract")
    configuration = load_corpus(ROOT / "catalog/corpus.toml")
    catalog = load_catalog(configuration, RAW_DIRECTORY)
    record = load_match_records(configuration, catalog, RAW_DIRECTORY, [MATCH_ID])[MATCH_ID]

    export = build_match_export(load_events(events_path, MATCH_ID), record)

    validate_export(export)
    cards = cast(list[Json], export["cards"])
    assert (
        sorted(
            (str(card["id"]), str(card["sentence"]), cast(Json, card["clock"])) for card in cards
        )
        == _golden_cards()
    )
    goals = cast(list[Json], export["goals"])
    assert goals[-1]["score"] == {"home": record.home_score, "away": record.away_score}
    assert len(cast(list[Json], export["periods"])) == 2
