"""Template wording: the numbers in the card, restated plainly."""

from regista.domain.entries import Channel
from regista.domain.events import ActionType, BallMovement, Event, MatchClock, Team
from regista.domain.geometry import Point
from regista.domain.ids import EventId, MatchId, TeamId
from regista.domain.insights import AttackingSideShift, ChannelCounts
from regista.templates import render_attacking_side_shift, render_clock, render_evidence


def card(channel: Channel, recent: ChannelCounts, baseline: ChannelCounts) -> AttackingSideShift:
    return AttackingSideShift(
        match_id=MatchId(1),
        team=Team(identifier=TeamId(1), name="Barcelona"),
        channel=channel,
        fired_at=MatchClock(period=2, minute=63, second=5),
        trigger_event_id=EventId("event-1"),
        recent=recent,
        baseline=baseline,
        recent_entry_ids=(),
        baseline_entry_ids=(),
        sources=("Synthetic",),
    )


def test_left_shift_sentence_matches_the_specification_example() -> None:
    shift = card(
        Channel.LEFT,
        recent=ChannelCounts(left=9, center=3, right=2),
        baseline=ChannelCounts(left=12, center=15, right=14),
    )

    assert render_attacking_side_shift(shift) == (
        "Barcelona's final-third entries have shifted to the left: "
        "9 of the last 14 (64%), up from 12 of 41 (29%) earlier."
    )


def test_center_shift_wording_and_halves_round_up() -> None:
    shift = card(
        Channel.CENTER,
        recent=ChannelCounts(left=1, center=5, right=2),
        baseline=ChannelCounts(left=7, center=1, right=0),
    )

    assert render_attacking_side_shift(shift) == (
        "Barcelona's final-third entries have shifted to the center: "
        "5 of the last 8 (63%), up from 1 of 8 (13%) earlier."
    )


def test_clock_shows_period_and_provider_minute() -> None:
    assert render_clock(MatchClock(period=2, minute=63, second=5)) == "period 2, 63:05"


def entry(identifier: str, period: int, minute: int, end_y: float) -> Event:
    start = Point(x=75.0, y=end_y)
    return Event(
        identifier=EventId(identifier),
        sequence=minute,
        match_id=MatchId(1),
        clock=MatchClock(period=period, minute=minute, second=0),
        team=Team(identifier=TeamId(1), name="Barcelona"),
        action=ActionType.PASS,
        location=start,
        movement=BallMovement(
            start=start, end=Point(x=85.0, y=end_y), completed=True, open_play=True
        ),
        source="Synthetic",
        provider_record={},
    )


def test_evidence_lists_the_channel_table_recent_entries_and_baseline_by_period() -> None:
    shift = card(
        Channel.LEFT,
        recent=ChannelCounts(left=2, center=0, right=0),
        baseline=ChannelCounts(left=0, center=1, right=1),
    )
    recent = [entry("r1", 2, 60, 10.0), entry("r2", 2, 61, 5.0)]
    baseline = [entry("b1", 1, 10, 40.0), entry("b2", 2, 50, 70.0)]

    assert render_evidence(shift, recent, baseline) == [
        "  channel recent          baseline        change",
        "  left    2 of 2   100%   0 of 2   0%     +100 points",
        "  center  0 of 2   0%     1 of 2   50%    -50 points",
        "  right   0 of 2   0%     1 of 2   50%    -50 points",
        "  recent window entries (period 2):",
        "    period 2, 60:00  pass   ( 75.0, 10.0) -> ( 85.0, 10.0)  left",
        "    period 2, 61:00  pass   ( 75.0,  5.0) -> ( 85.0,  5.0)  left",
        "  baseline entries by period:",
        "    period 1: left 0, center 1, right 0",
        "    period 2: left 0, center 0, right 1",
    ]
