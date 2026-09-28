"""Fan-value probe 01: timeline sheets of observations for three replayed matches.

Research code, not a detector (see ``docs/research/probe-01.md``). It combines the
Phase 1 side-shift cards with three throwaway prototype observations. Every
prototype is computed point-in-time: at each event it reads only events at or
before that event. The prototype thresholds below were fixed before the first
run and are initial guesses, not tuned values.

Run: ``uv run python scripts/research/probe_01.py``. Sheets are written to
``out/probe-01/`` (git-ignored).
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from regista.adapters.statsbomb.events import load_events
from regista.detectors.attacking_side_shift import AttackingSideShiftDetector, SideShiftSettings
from regista.domain.ids import MatchId
from regista.domain.replay import replay
from regista.pipeline.catalog import load_corpus
from regista.templates import render_attacking_side_shift

# The note this script supports used the Phase 1 rule: evaluate teams at every event.
PHASE_ONE_TIMING = SideShiftSettings(fire_on_own_entry=False)

STATSBOMB_DATA = (
    Path("data/raw/statsbomb-open-data")
    / load_corpus(Path("catalog/corpus.toml")).source_commit
    / "data"
)
# (match identifier, competition identifier, season identifier)
PROBE_MATCHES = ((265958, 11, 27), (3869420, 43, 106), (3869321, 43, 106))

WINDOW_SECONDS = 600
COOLDOWN_SECONDS = 600
PENALTY_SHOOTOUT_PERIOD = 5
SET_PIECE_PASS_TYPES = frozenset({"Corner", "Free Kick", "Throw-in", "Goal Kick", "Kick Off"})
SENDING_OFF_CARDS = frozenset({"Red Card", "Second Yellow"})

# Territory: share of completed open-play passes starting at x >= 80 (field tilt).
TERRITORY_MINIMUM_RECENT_PASSES = 10
TERRITORY_MINIMUM_BASELINE_PASSES = 20
TERRITORY_MINIMUM_SHARE = 0.65
TERRITORY_MINIMUM_INCREASE = 0.20
# Involvement: one player's share of his team's open-play pass attempts.
INVOLVEMENT_MINIMUM_TEAM_RECENT_PASSES = 25
INVOLVEMENT_MINIMUM_BASELINE_TEAM_PASSES = 40
INVOLVEMENT_MINIMUM_SHARE = 0.20
INVOLVEMENT_MINIMUM_INCREASE = 0.10
# Chances: shots in the window against the team's earlier shot rate.
CHANCES_MINIMUM_RECENT_SHOTS = 3
CHANCES_MINIMUM_RATE_RATIO = 2.0
CHANCES_MINIMUM_BASELINE_MINUTES = 20

SIDE_SHIFT = "Attacking side"
TERRITORY = "Territory"
INVOLVEMENT = "Involvement"
CHANCES = "Chances"
PROTOTYPES = (TERRITORY, INVOLVEMENT, CHANCES)

Record = dict[str, object]


@dataclass(frozen=True, slots=True)
class Observation:
    period: int
    minute: int
    second: int
    kind: str
    text: str


@dataclass(frozen=True, slots=True)
class PassRecord:
    team: str
    passer: int
    period: int
    seconds: int
    open_play: bool
    completed: bool
    start_x: float
    teammates_on_pitch: frozenset[int]


@dataclass(frozen=True, slots=True)
class ShotRecord:
    team: str
    period: int
    seconds: int
    expected_goals: float


def _details(record: Record, key: str) -> Record:
    return cast(Record, record.get(key, {}))


def _name(value: object) -> str:
    return cast(str, cast(Record, value)["name"])


def _percent(numerator: int, denominator: int) -> int:
    return round(100 * numerator / denominator)


class ProbeState:
    """Everything seen so far in one match, in replay order."""

    def __init__(self, display_names: dict[int, str]) -> None:
        self.display_names = display_names
        self.teams: list[str] = []
        self.on_pitch: dict[str, set[int]] = {}
        self.passes: list[PassRecord] = []
        self.shots: list[ShotRecord] = []
        self.period_start: dict[int, int] = {}
        self.period_last: dict[int, int] = {}
        self.cooldowns: dict[tuple[str, str], tuple[int, int]] = {}
        # (kind, team) -> {(period, minute): could the prototype be evaluated?}
        self.evaluable: dict[tuple[str, str], dict[tuple[int, int], bool]] = {}

    def record(self, event: Record) -> None:
        period = cast(int, event["period"])
        seconds = cast(int, event["minute"]) * 60 + cast(int, event["second"])
        team = _name(event["team"])
        self.period_start.setdefault(period, seconds)
        self.period_last[period] = seconds
        if team not in self.teams:
            self.teams.append(team)
            self.on_pitch[team] = set()
        kind = _name(event["type"])
        if kind == "Starting XI":
            lineup = cast(list[Record], _details(event, "tactics")["lineup"])
            self.on_pitch[team] = {cast(int, _details(entry, "player")["id"]) for entry in lineup}
        elif kind == "Substitution":
            self.on_pitch[team].discard(cast(int, _details(event, "player")["id"]))
            replacement = _details(_details(event, "substitution"), "replacement")
            self.on_pitch[team].add(cast(int, replacement["id"]))
        elif kind == "Pass":
            details = _details(event, "pass")
            pass_type = _details(details, "type").get("name")
            self.passes.append(
                PassRecord(
                    team=team,
                    passer=cast(int, _details(event, "player")["id"]),
                    period=period,
                    seconds=seconds,
                    open_play=pass_type not in SET_PIECE_PASS_TYPES,
                    completed="outcome" not in details,
                    start_x=cast(list[float], event["location"])[0],
                    teammates_on_pitch=frozenset(self.on_pitch[team]),
                )
            )
        elif kind == "Shot" and period != PENALTY_SHOOTOUT_PERIOD:
            expected_goals = cast(float, _details(event, "shot").get("statsbomb_xg", 0.0))
            self.shots.append(ShotRecord(team, period, seconds, expected_goals))
        for key in ("foul_committed", "bad_behaviour"):
            card = _details(_details(event, key), "card").get("name")
            if card in SENDING_OFF_CARDS:
                self.on_pitch[team].discard(cast(int, _details(event, "player")["id"]))


def _in_window(period: int, seconds: int, now_period: int, now_seconds: int) -> bool:
    return period == now_period and seconds > now_seconds - WINDOW_SECONDS


def _territory(state: ProbeState, team: str, period: int, now: int) -> str | None | bool:
    """Return card text, None for no change, or False when it cannot be evaluated."""
    final_third = [p for p in state.passes if p.open_play and p.completed and p.start_x >= 80]
    recent = [p for p in final_third if _in_window(p.period, p.seconds, period, now)]
    baseline = [p for p in final_third if not _in_window(p.period, p.seconds, period, now)]
    if len(recent) < TERRITORY_MINIMUM_RECENT_PASSES:
        return False
    if len(baseline) < TERRITORY_MINIMUM_BASELINE_PASSES:
        return False
    own_recent = sum(p.team == team for p in recent)
    own_baseline = sum(p.team == team for p in baseline)
    recent_share = own_recent / len(recent)
    baseline_share = own_baseline / len(baseline)
    if recent_share < TERRITORY_MINIMUM_SHARE:
        return None
    if recent_share - baseline_share < TERRITORY_MINIMUM_INCREASE:
        return None
    shots = [
        s for s in state.shots if s.team == team and _in_window(s.period, s.seconds, period, now)
    ]
    expected_goals = sum(s.expected_goals for s in shots)
    return (
        f"{team} have taken over the final third: {own_recent} of the last {len(recent)} "
        f"completed passes there ({_percent(own_recent, len(recent))}%), up from "
        f"{_percent(own_baseline, len(baseline))}% earlier. Their shots in the last 10 minutes: "
        f"{len(shots)} ({expected_goals:.2f} xG)."
    )


def _involvement(state: ProbeState, team: str, period: int, now: int) -> str | None | bool:
    team_passes = [p for p in state.passes if p.team == team and p.open_play]
    recent = [p for p in team_passes if _in_window(p.period, p.seconds, period, now)]
    if len(recent) < INVOLVEMENT_MINIMUM_TEAM_RECENT_PASSES:
        return False
    best: tuple[float, str] | None = None
    any_evaluable = False
    for player in sorted(state.on_pitch[team]):
        baseline = [
            p
            for p in team_passes
            if player in p.teammates_on_pitch and not _in_window(p.period, p.seconds, period, now)
        ]
        if len(baseline) < INVOLVEMENT_MINIMUM_BASELINE_TEAM_PASSES:
            continue
        any_evaluable = True
        own_recent = sum(p.passer == player for p in recent)
        own_baseline = sum(p.passer == player for p in baseline)
        recent_share = own_recent / len(recent)
        increase = recent_share - own_baseline / len(baseline)
        if recent_share < INVOLVEMENT_MINIMUM_SHARE or increase < INVOLVEMENT_MINIMUM_INCREASE:
            continue
        if best is None or increase > best[0]:
            name = state.display_names.get(player, str(player))
            best = (
                increase,
                f"{name} has been much more involved for {team}: {own_recent} of their last "
                f"{len(recent)} passes ({_percent(own_recent, len(recent))}%), up from "
                f"{_percent(own_baseline, len(baseline))}% earlier while on the pitch.",
            )
    if not any_evaluable:
        return False
    return None if best is None else best[1]


def _chances(state: ProbeState, team: str, period: int, now: int) -> str | None | bool:
    window_start = now - WINDOW_SECONDS
    baseline_seconds = sum(
        state.period_last[p] - state.period_start[p] for p in state.period_start if p < period
    ) + max(0, window_start - state.period_start[period])
    if baseline_seconds < CHANCES_MINIMUM_BASELINE_MINUTES * 60:
        return False
    shots = [s for s in state.shots if s.team == team]
    recent = [s for s in shots if _in_window(s.period, s.seconds, period, now)]
    baseline = [s for s in shots if not _in_window(s.period, s.seconds, period, now)]
    if len(recent) < CHANCES_MINIMUM_RECENT_SHOTS:
        return None
    recent_rate = len(recent) / (WINDOW_SECONDS / 60)
    baseline_rate = len(baseline) / (baseline_seconds / 60)
    if baseline and recent_rate < CHANCES_MINIMUM_RATE_RATIO * baseline_rate:
        return None
    return (
        f"{team}'s chances have picked up: {len(recent)} shots "
        f"({sum(s.expected_goals for s in recent):.2f} xG) in the last 10 minutes, after "
        f"{len(baseline)} shots ({sum(s.expected_goals for s in baseline):.2f} xG) in the "
        f"{round(baseline_seconds / 60)} minutes before."
    )


PROTOTYPE_RULES = {TERRITORY: _territory, INVOLVEMENT: _involvement, CHANCES: _chances}


def prototype_observations(events: list[Record], state: ProbeState) -> list[Observation]:
    observations: list[Observation] = []
    for event in sorted(events, key=lambda record: cast(int, record["index"])):
        state.record(event)
        period = cast(int, event["period"])
        minute, second = cast(int, event["minute"]), cast(int, event["second"])
        now = minute * 60 + second
        if period == PENALTY_SHOOTOUT_PERIOD or now - state.period_start[period] < WINDOW_SECONDS:
            continue
        for team in state.teams:
            for kind in PROTOTYPES:
                cooldown = state.cooldowns.get((kind, team))
                if cooldown is not None and cooldown[0] == period and now < cooldown[1]:
                    continue
                result = PROTOTYPE_RULES[kind](state, team, period, now)
                state.evaluable.setdefault((kind, team), {})[(period, minute)] = result is not False
                if isinstance(result, str):
                    observations.append(Observation(period, minute, second, kind, result))
                    state.cooldowns[(kind, team)] = (period, now + COOLDOWN_SECONDS)
    return observations


def side_shift_observations(match_id: int) -> list[Observation]:
    events = load_events(STATSBOMB_DATA / "events" / f"{match_id}.json", MatchId(match_id))
    return [
        Observation(
            card.fired_at.period,
            card.fired_at.minute,
            card.fired_at.second,
            SIDE_SHIFT,
            render_attacking_side_shift(card),
        )
        for card in replay(events, AttackingSideShiftDetector(PHASE_ONE_TIMING))
    ]


def _read(path: Path) -> object:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _display_names(match_id: int) -> dict[int, str]:
    lineups = cast(list[Record], _read(STATSBOMB_DATA / "lineups" / f"{match_id}.json"))
    names: dict[int, str] = {}
    for team in lineups:
        for player in cast(list[Record], team["lineup"]):
            nickname = player.get("player_nickname")
            names[cast(int, player["player_id"])] = cast(str, nickname or player["player_name"])
    return names


def build_sheet(match_id: int, competition: int, season: int) -> tuple[str, list[Observation]]:
    matches = cast(
        list[Record], _read(STATSBOMB_DATA / "matches" / str(competition) / f"{season}.json")
    )
    match = next(m for m in matches if m["match_id"] == match_id)
    home = cast(str, _details(match, "home_team")["home_team_name"])
    away = cast(str, _details(match, "away_team")["away_team_name"])
    competition_name = cast(str, _details(match, "competition")["competition_name"])
    events = cast(list[Record], _read(STATSBOMB_DATA / "events" / f"{match_id}.json"))
    state = ProbeState(_display_names(match_id))
    observations = side_shift_observations(match_id) + prototype_observations(events, state)
    observations.sort(key=lambda o: (o.period, o.minute, o.second))

    lines = [
        f"# Probe 01: {home} v {away}",
        "",
        f"{competition_name}, {match['match_date']}. StatsBomb match {match_id}.",
        "",
        "Read one row at a time as the replay reaches its time; do not read ahead. "
        "Times are the provider's match clock (period, minute:second). "
        "Fill in the columns as you go; leave a cell empty if unsure.",
        "",
        "| # | Time | Type | Observation | Correct? | Timely? | Added understanding? "
        "| Attention cost | Repetitive? | Keep or drop | Better at halftime or after? | Notes |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for number, observation in enumerate(observations, start=1):
        time = f"P{observation.period} {observation.minute:02d}:{observation.second:02d}"
        lines.append(
            f"| {number} | {time} | {observation.kind} | {observation.text} "
            "|  |  |  |  |  |  |  |  |"
        )
    if not observations:
        lines.append("| — | — | — | No observations in this match. |  |  |  |  |  |  |  |  |")
    lines += ["", "## Could not evaluate (insufficient data)", ""]
    lines.append(
        "Minutes in which a prototype could not judge a team, out of the minutes it checked "
        "(minutes inside a cooldown after a card are not checked)."
    )
    lines.append("The Phase 1 side-shift detector does not report this yet.")
    lines.append("")
    for kind in PROTOTYPES:
        for team in state.teams:
            minutes = state.evaluable.get((kind, team), {})
            missing = sum(not ok for ok in minutes.values())
            lines.append(f"- {kind}, {team}: {missing} of {len(minutes)} minutes")
    lines += ["", "Data: StatsBomb", ""]
    return "\n".join(lines), observations


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("out/probe-01"))
    arguments = parser.parse_args(argv)
    output: Path = arguments.output
    output.mkdir(parents=True, exist_ok=True)
    for match_id, competition, season in PROBE_MATCHES:
        sheet, observations = build_sheet(match_id, competition, season)
        (output / f"{match_id}.md").write_text(sheet, encoding="utf-8")
        counts = {kind: 0 for kind in (SIDE_SHIFT, *PROTOTYPES)}
        for observation in observations:
            counts[observation.kind] += 1
        print(match_id, counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
