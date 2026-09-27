"""Provider-independent rows for the normalized warehouse layer.

An adapter turns one provider match into a ``NormalizedMatch``; the warehouse
stores it. Each field is tagged in ``FIELD_AVAILABILITY`` with when it becomes
known (see the Phase 2 specification). Detectors may read only
``known_at_event`` and ``delayed`` fields; ``hindsight`` fields are for
retrospective research only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from regista.domain.events import Event
from regista.domain.geometry import Point
from regista.domain.ids import EventId, MatchId, PlayerId, TeamId
from regista.domain.lineups import Appearance, PositionSpell
from regista.domain.matches import MatchRecord

Availability = Literal["known_at_event", "delayed", "hindsight"]
Severity = Literal["blocking", "warning"]


@dataclass(frozen=True, slots=True)
class EventRow:
    """The event spine: a domain event plus the columns the warehouse needs."""

    event: Event
    period_seconds: float
    provider_event_type: str
    player_id: PlayerId | None
    position: str | None
    possession: int | None
    possession_team_id: TeamId | None
    under_pressure: bool


@dataclass(frozen=True, slots=True)
class PassRow:
    event_id: EventId
    recipient_player_id: PlayerId | None
    completed: bool
    outcome: str | None
    pass_type: str | None
    set_piece_type: str | None
    open_play: bool
    height: str | None
    is_cross: bool
    is_shot_assist: bool
    is_goal_assist: bool


@dataclass(frozen=True, slots=True)
class ShotRow:
    event_id: EventId
    provider_xg: float | None
    outcome: str
    is_goal: bool
    shot_type: str
    body_part: str | None
    key_pass_event_id: EventId | None
    end_location: Point | None
    end_z: float | None


@dataclass(frozen=True, slots=True)
class SubstitutionRow:
    event_id: EventId
    team_id: TeamId
    player_off_id: PlayerId
    player_on_id: PlayerId
    reason: str | None


@dataclass(frozen=True, slots=True)
class FormationChangeRow:
    event_id: EventId
    team_id: TeamId
    formation: str
    kind: Literal["starting", "tactical_shift"]


@dataclass(frozen=True, slots=True)
class GoalRow:
    """A goal derived from a scoring shot or an own goal.

    ``in_shootout`` goals decide nothing about the score and are excluded from
    score states and from reconciliation with the final score.
    """

    event_id: EventId
    scoring_team_id: TeamId
    kind: Literal["shot", "own_goal"]
    in_shootout: bool


@dataclass(frozen=True, slots=True)
class NormalizedMatch:
    match: MatchRecord
    appearances: tuple[Appearance, ...]
    position_spells: tuple[PositionSpell, ...]
    events: tuple[EventRow, ...]
    passes: tuple[PassRow, ...]
    shots: tuple[ShotRow, ...]
    substitutions: tuple[SubstitutionRow, ...]
    formation_changes: tuple[FormationChangeRow, ...]
    goals: tuple[GoalRow, ...]


@dataclass(frozen=True, slots=True)
class QualityCheck:
    """One data-quality result for one match."""

    match_id: MatchId
    check: str
    severity: Severity
    passed: bool
    detail: str


# When each normalized field becomes known. A field whose timing is unclear
# counts as hindsight until a contract test shows otherwise.
FIELD_AVAILABILITY: dict[tuple[str, str], tuple[Availability, str]] = {
    ("events", "sequence"): ("known_at_event", "provider order"),
    ("events", "period"): ("known_at_event", ""),
    ("events", "period_seconds"): ("known_at_event", "provider timestamp; may step backwards"),
    ("events", "team_id"): ("known_at_event", ""),
    ("events", "player_id"): ("known_at_event", ""),
    ("events", "position"): ("known_at_event", ""),
    ("events", "event_type"): ("known_at_event", ""),
    ("events", "x"): ("known_at_event", ""),
    ("events", "y"): ("known_at_event", ""),
    ("events", "end_x"): ("delayed", "carries are built from the next action"),
    ("events", "end_y"): ("delayed", "carries are built from the next action"),
    ("events", "under_pressure"): ("hindsight", "timing unclear; not yet contract-tested"),
    ("events", "possession"): ("hindsight", "possession grouping is post-processed"),
    ("events", "possession_team_id"): ("hindsight", "possession grouping is post-processed"),
    ("events", "provider_record"): ("hindsight", "contains forward links and hindsight flags"),
    ("passes", "recipient_player_id"): ("delayed", "known once the ball is received"),
    ("passes", "completed"): ("known_at_event", ""),
    ("passes", "outcome"): ("known_at_event", ""),
    ("passes", "pass_type"): ("known_at_event", ""),
    ("passes", "set_piece_type"): ("known_at_event", ""),
    ("passes", "open_play"): ("known_at_event", "from the pass type, never play_pattern"),
    ("passes", "height"): ("known_at_event", ""),
    ("passes", "is_cross"): ("known_at_event", ""),
    ("passes", "is_shot_assist"): ("hindsight", "set when a later shot follows"),
    ("passes", "is_goal_assist"): ("hindsight", "set when a later goal follows"),
    ("shots", "provider_xg"): ("known_at_event", "the provider's model, not Regista's"),
    ("shots", "outcome"): ("known_at_event", ""),
    ("shots", "is_goal"): ("known_at_event", ""),
    ("shots", "shot_type"): ("known_at_event", ""),
    ("shots", "body_part"): ("known_at_event", ""),
    ("shots", "key_pass_event_id"): ("known_at_event", "backward link to an earlier pass"),
    ("shots", "end_x"): ("known_at_event", ""),
    ("shots", "end_y"): ("known_at_event", ""),
    ("shots", "end_z"): ("known_at_event", ""),
    ("substitutions", "player_off_id"): ("known_at_event", ""),
    ("substitutions", "player_on_id"): ("known_at_event", ""),
    ("substitutions", "reason"): ("known_at_event", ""),
    ("formation_changes", "formation"): ("known_at_event", ""),
    ("goals", "scoring_team_id"): ("known_at_event", ""),
    ("matches", "home_score"): ("hindsight", "final score"),
    ("matches", "away_score"): ("hindsight", "final score"),
    ("position_spells", "end_period"): ("hindsight", "known when the spell ends"),
    ("position_spells", "end_period_seconds"): ("hindsight", "known when the spell ends"),
}
