"""Audit side-shift cards on acquired development matches only.

Run: ``uv run python scripts/research/phase2_card_audit.py``.
The output contains aggregate diagnostics, not provider records or fan judgments.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from typing import cast

from regista.adapters.statsbomb.events import load_events
from regista.detectors.attacking_side_shift import AttackingSideShiftDetector
from regista.domain.entries import Channel, is_final_third_entry
from regista.domain.events import Event
from regista.domain.ids import EventId, MatchId
from regista.domain.replay import replay
from regista.pipeline.catalog import load_corpus

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw"
MANIFEST = RAW / "manifest.jsonl"
SPLIT = ROOT / "splits/v1.json"


def _development_ids() -> set[int]:
    payload: object = json.loads(SPLIT.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("split file has no assignments")
    split = cast(dict[str, object], payload)
    if not isinstance(split.get("assignments"), list):
        raise ValueError("split file has no assignments")
    assignments = cast(list[dict[str, object]], split["assignments"])
    identifiers: set[int] = set()
    for row in assignments:
        identifier = row["match_id"]
        if not isinstance(identifier, int):
            raise ValueError("split has a nonnumeric match identifier")
        if row["bucket"] == "development":
            identifiers.add(identifier)
    return identifiers


def _event_files(development_ids: set[int]) -> dict[int, Path]:
    source_commit = load_corpus(ROOT / "catalog/corpus.toml").source_commit
    files: dict[int, Path] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        receipt = cast(dict[str, object], json.loads(line))
        if receipt.get("kind") != "events":
            continue
        identifier = int(cast(int, receipt["provider_match_id"]))
        if receipt.get("split_bucket") != "development" or identifier not in development_ids:
            raise ValueError(f"event receipt {identifier} is outside development")
        if receipt.get("source_commit") != source_commit or identifier in files:
            raise ValueError(f"event receipt {identifier} has a wrong source or duplicate")
        path = RAW / str(receipt["relative_path"])
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256(path.read_bytes()).hexdigest() != receipt.get("sha256"):
            raise ValueError(f"event file {identifier} differs from its receipt")
        files[identifier] = path
    if not files:
        raise ValueError("no development event files found")
    return files


def _check_evidence(
    card_ids: tuple[EventId, ...], events: dict[EventId, Event], trigger: Event, team_id: int
) -> None:
    if len(card_ids) != len(set(card_ids)):
        raise ValueError("card repeats an evidence event")
    for identifier in card_ids:
        evidence = events[identifier]
        if evidence.sequence > trigger.sequence or evidence.team.identifier != team_id:
            raise ValueError("card evidence is future or belongs to another team")
        if not is_final_third_entry(evidence):
            raise ValueError("card evidence is not a final-third entry")


def audit() -> dict[str, object]:
    files = _event_files(_development_ids())
    cards_by_match: Counter[int] = Counter()
    cards_by_channel: Counter[str] = Counter()
    unusual: Counter[str] = Counter()
    future_eligible = 0
    future_shift_sustained = 0
    future_at_least_recent = 0
    examples: dict[str, list[dict[str, object]]] = defaultdict(list)

    for match_id, path in sorted(files.items()):
        match_events = load_events(path, MatchId(match_id))
        by_id = {event.identifier: event for event in match_events}
        if len(by_id) != len(match_events):
            raise ValueError(f"match {match_id} repeats an event identifier")
        entries_by_team: dict[int, list[Event]] = defaultdict(list)
        for event in match_events:
            if is_final_third_entry(event):
                entries_by_team[event.team.identifier].append(event)
        last_card: dict[tuple[int, str], Event] = {}

        for card in replay(match_events, AttackingSideShiftDetector()):
            trigger = by_id[card.trigger_event_id]
            team_id = int(card.team.identifier)
            if trigger.clock != card.fired_at:
                raise ValueError("card clock differs from its trigger")
            if set(card.recent_entry_ids) & set(card.baseline_entry_ids):
                raise ValueError("recent and baseline evidence overlap")
            if len(card.recent_entry_ids) != card.recent.total:
                raise ValueError("recent evidence count differs from card")
            if len(card.baseline_entry_ids) != card.baseline.total:
                raise ValueError("baseline evidence count differs from card")
            _check_evidence(
                card.recent_entry_ids + card.baseline_entry_ids, by_id, trigger, team_id
            )
            if card.sources != tuple(
                sorted(
                    {
                        by_id[identifier].source
                        for identifier in card.recent_entry_ids + card.baseline_entry_ids
                    }
                )
            ):
                raise ValueError("card sources differ from evidence")

            cards_by_match[match_id] += 1
            cards_by_channel[card.channel.value] += 1
            if trigger.team.identifier != card.team.identifier:
                unusual["triggered_by_other_team"] += 1
            if card.recent.total <= 10:
                unusual["at_most_ten_recent_entries"] += 1
            named_count = card.recent.count(card.channel)
            if named_count < max(card.recent.count(channel) for channel in Channel):
                unusual["named_channel_not_plurality"] += 1
                if len(examples["named_channel_not_plurality"]) < 5:
                    examples["named_channel_not_plurality"].append(
                        {
                            "match_id": match_id,
                            "period": card.fired_at.period,
                            "minute": card.fired_at.minute,
                            "team": card.team.name,
                            "channel": card.channel.value,
                            "recent": [card.recent.left, card.recent.center, card.recent.right],
                        }
                    )
            previous = last_card.get((team_id, card.channel.value))
            if previous is not None:
                unusual["repeated_team_channel_in_match"] += 1
            last_card[(team_id, card.channel.value)] = trigger

            future = [
                entry
                for entry in entries_by_team[team_id]
                if entry.clock.period == card.fired_at.period
                and trigger.sequence < entry.sequence
                and card.fired_at.elapsed_seconds
                < entry.clock.elapsed_seconds
                <= card.fired_at.elapsed_seconds + 600
            ]
            if len(future) >= 8:
                future_eligible += 1
                future_named = sum(
                    1
                    for entry in future
                    if entry.movement is not None
                    and (
                        Channel.LEFT
                        if entry.movement.end.y < 80 / 3
                        else Channel.RIGHT
                        if entry.movement.end.y > 160 / 3
                        else Channel.CENTER
                    )
                    is card.channel
                )
                future_share = future_named / len(future)
                if future_share >= float(card.baseline.share(card.channel)) + 0.25:
                    future_shift_sustained += 1
                if future_share >= float(card.recent.share(card.channel)):
                    future_at_least_recent += 1

    counts = Counter(cards_by_match.values())
    counts[0] = len(files) - len(cards_by_match)
    return {
        "development_matches": len(files),
        "cards": sum(cards_by_match.values()),
        "matches_with_cards": len(cards_by_match),
        "cards_per_match": dict(sorted(counts.items())),
        "maximum_cards_in_one_match": max(cards_by_match.values(), default=0),
        "cards_by_channel": dict(sorted(cards_by_channel.items())),
        "diagnostics": dict(sorted(unusual.items())),
        "future_ten_minute_windows_with_at_least_eight_entries": future_eligible,
        "future_share_at_least_baseline_plus_25_points": future_shift_sustained,
        "future_share_at_least_recent_share": future_at_least_recent,
        "illustrative_cases": dict(examples),
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
