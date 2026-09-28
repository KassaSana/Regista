"""Independently check flagged side-shift cards against raw development events.

Run: ``uv run python scripts/research/phase2_flagged_card_audit.py``.
Only aggregate diagnostics and a few development examples are printed.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from phase2_card_audit import development_event_files, development_ids

from regista.adapters.statsbomb.events import load_events
from regista.detectors.attacking_side_shift import AttackingSideShiftDetector, SideShiftSettings
from regista.domain.ids import MatchId
from regista.domain.replay import replay

# The note this script supports used the Phase 1 rule: evaluate teams at every event.
PHASE_ONE_TIMING = SideShiftSettings(fire_on_own_entry=False)

CHANNELS = ("left", "center", "right")
SET_PIECES = frozenset({"Corner", "Free Kick", "Throw-in", "Goal Kick", "Kick Off"})
OPEN_PLAY_PASS_TYPES = frozenset({"Recovery", "Interception"})


@dataclass(frozen=True, slots=True)
class RawEntry:
    """A final-third entry classified directly from one provider record."""

    identifier: str
    sequence: int
    period: int
    seconds: int
    team_id: int
    channel: str


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("expected a provider object")
    return cast(dict[str, object], value)


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("expected a provider integer")
    return value


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("expected a provider coordinate")
    return float(value)


def _point(value: object) -> tuple[float, float]:
    if not isinstance(value, list):
        raise ValueError("expected two provider coordinates")
    coordinates = cast(list[object], value)
    if len(coordinates) != 2:
        raise ValueError("expected two provider coordinates")
    return _number(coordinates[0]), _number(coordinates[1])


def _clock(record: dict[str, object]) -> tuple[int, int]:
    return _integer(record["period"]), 60 * _integer(record["minute"]) + _integer(record["second"])


def _raw_entry(record: dict[str, object]) -> RawEntry | None:
    kind = _mapping(record["type"]).get("name")
    if kind == "Pass":
        details = _mapping(record["pass"])
        pass_type_value = details.get("type")
        pass_type = None if pass_type_value is None else _mapping(pass_type_value).get("name")
        if pass_type is not None and pass_type not in SET_PIECES | OPEN_PLAY_PASS_TYPES:
            raise ValueError(f"unknown pass type {pass_type}")
        if "outcome" in details or pass_type in SET_PIECES:
            return None
    elif kind == "Carry":
        details = _mapping(record["carry"])
    else:
        return None
    start_x, _ = _point(record["location"])
    end_x, end_y = _point(details["end_location"])
    if not start_x < 80 <= end_x:
        return None
    identifier = record["id"]
    if not isinstance(identifier, str):
        raise ValueError("expected a provider event identifier")
    period, seconds = _clock(record)
    return RawEntry(
        identifier=identifier,
        sequence=_integer(record["index"]),
        period=period,
        seconds=seconds,
        team_id=_integer(_mapping(record["team"])["id"]),
        channel="left" if end_y < 80 / 3 else "right" if end_y > 160 / 3 else "center",
    )


def _load_raw(path: Path) -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path} is not a provider event list")
    records = [_mapping(value) for value in cast(list[object], payload)]
    records.sort(key=lambda record: _integer(record["index"]))
    by_id = {cast(str, record["id"]): record for record in records}
    if len(by_id) != len(records):
        raise ValueError(f"{path} repeats a provider event identifier")
    return records, by_id


def _counts(entries: list[RawEntry]) -> tuple[int, int, int]:
    return (
        sum(entry.channel == "left" for entry in entries),
        sum(entry.channel == "center" for entry in entries),
        sum(entry.channel == "right" for entry in entries),
    )


def audit() -> dict[str, object]:
    files = development_event_files(development_ids())
    totals: Counter[str] = Counter()
    opponent_causes: Counter[str] = Counter()
    opponent_gaps: Counter[str] = Counter()
    non_plurality_by_channel: Counter[str] = Counter()
    examples: dict[str, list[dict[str, object]]] = defaultdict(list)

    for match_id, path in sorted(files.items()):
        records, raw_by_id = _load_raw(path)
        raw_positions = {
            cast(str, record["id"]): position for position, record in enumerate(records)
        }
        entries_by_team: dict[int, list[RawEntry]] = defaultdict(list)
        period_starts: dict[int, int] = {}
        for record in records:
            record_period, record_seconds = _clock(record)
            period_starts.setdefault(record_period, record_seconds)
            entry = _raw_entry(record)
            if entry is not None:
                entries_by_team[entry.team_id].append(entry)
        previous_card_clock: dict[int, tuple[int, int]] = {}
        normalized = load_events(path, MatchId(match_id))

        for card in replay(normalized, AttackingSideShiftDetector(PHASE_ONE_TIMING)):
            totals["cards"] += 1
            trigger = raw_by_id[str(card.trigger_event_id)]
            trigger_sequence = _integer(trigger["index"])
            period, now = _clock(trigger)
            team_id = int(card.team.identifier)
            if (period, now) != (card.fired_at.period, card.fired_at.elapsed_seconds):
                raise ValueError("raw and normalized trigger clocks differ")
            prefix = [
                entry for entry in entries_by_team[team_id] if entry.sequence <= trigger_sequence
            ]
            recent = [
                entry for entry in prefix if entry.period == period and entry.seconds > now - 600
            ]
            baseline = [
                entry
                for entry in prefix
                if not (entry.period == period and entry.seconds > now - 600)
            ]
            if tuple(entry.identifier for entry in recent) != card.recent_entry_ids:
                raise ValueError(f"match {match_id} recent evidence differs from raw records")
            if tuple(entry.identifier for entry in baseline) != card.baseline_entry_ids:
                raise ValueError(f"match {match_id} baseline evidence differs from raw records")
            if _counts(recent) != (card.recent.left, card.recent.center, card.recent.right):
                raise ValueError(f"match {match_id} recent counts differ from raw records")
            if _counts(baseline) != (card.baseline.left, card.baseline.center, card.baseline.right):
                raise ValueError(f"match {match_id} baseline counts differ from raw records")
            totals["raw_recomputed_cards"] += 1

            recent_counts = _counts(recent)
            named_count = recent_counts[CHANNELS.index(card.channel.value)]
            if named_count < max(recent_counts):
                totals["non_plurality_cards"] += 1
                non_plurality_by_channel[card.channel.value] += 1
                if len(examples["non_plurality"]) < 5:
                    examples["non_plurality"].append(
                        {
                            "match_id": match_id,
                            "period": period,
                            "seconds": now,
                            "team": card.team.name,
                            "channel": card.channel.value,
                            "recent": recent_counts,
                            "baseline": _counts(baseline),
                        }
                    )

            trigger_team_id = _integer(_mapping(trigger["team"])["id"])
            if trigger_team_id != team_id:
                totals["other_team_triggers"] += 1
                position = raw_positions[str(card.trigger_event_id)]
                previous = records[position - 1] if position else None
                prior_period, prior_seconds = _clock(previous) if previous else (0, -1)
                expired = prior_period == period and any(
                    entry.sequence < trigger_sequence
                    and entry.period == period
                    and prior_seconds - 600 < entry.seconds <= now - 600
                    for entry in prefix
                )
                prior_card = previous_card_clock.get(team_id)
                cooldown_ended = (
                    prior_card is not None
                    and prior_card[0] == period
                    and prior_period == period
                    and prior_seconds < prior_card[1] + 600 <= now
                )
                first_full_window = (
                    prior_period == period
                    and prior_seconds - period_starts[period] < 600 <= now - period_starts[period]
                )
                if expired:
                    opponent_causes["window_entry_expired"] += 1
                if cooldown_ended:
                    opponent_causes["cooldown_ended"] += 1
                if first_full_window:
                    opponent_causes["first_full_window"] += 1
                if not (expired or cooldown_ended or first_full_window):
                    opponent_causes["unexplained_by_these_checks"] += 1

                last_own = next(
                    (entry for entry in reversed(prefix) if entry.period == period), None
                )
                if last_own is None:
                    opponent_gaps["no_current_period_entry"] += 1
                    gap: int | None = None
                else:
                    gap = now - last_own.seconds
                    if gap < 0:
                        opponent_gaps["clock_reversed"] += 1
                    elif gap <= 30:
                        opponent_gaps["up_to_30_seconds"] += 1
                    elif gap <= 60:
                        opponent_gaps["31_to_60_seconds"] += 1
                    elif gap <= 180:
                        opponent_gaps["61_to_180_seconds"] += 1
                    else:
                        opponent_gaps["over_180_seconds"] += 1
                if len(examples["other_team_trigger"]) < 5:
                    examples["other_team_trigger"].append(
                        {
                            "match_id": match_id,
                            "period": period,
                            "seconds": now,
                            "team": card.team.name,
                            "last_entry_gap_seconds": gap,
                            "entry_expired": expired,
                            "cooldown_ended": cooldown_ended,
                            "first_full_window": first_full_window,
                        }
                    )
            previous_card_clock[team_id] = period, now

    return {
        "development_matches": len(files),
        "counts": dict(sorted(totals.items())),
        "non_plurality_by_channel": dict(sorted(non_plurality_by_channel.items())),
        "other_team_trigger_mechanisms": dict(sorted(opponent_causes.items())),
        "other_team_trigger_gap_from_last_own_entry": dict(sorted(opponent_gaps.items())),
        "illustrative_development_cases": dict(examples),
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
