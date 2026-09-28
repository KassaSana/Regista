"""Template wording: the numbers in the card, restated plainly."""

from dataclasses import replace

from regista.domain.entries import Channel
from regista.domain.events import ActionType, BallMovement, Event, MatchClock, Team
from regista.domain.geometry import Point
from regista.domain.ids import EventId, MatchId, TeamId
from regista.domain.insights import AttackingBurst, AttackingSideShift, ChannelCounts
from regista.templates import (
    render_attacking_burst,
    render_attacking_side_shift,
    render_clock,
    render_evidence,
)


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
        "More of Barcelona's final-third entries are ending on the left: "
        "9 of the last 14 (64%), up from 12 of 41 (29%) earlier."
    )


def test_center_shift_wording_and_halves_round_up() -> None:
    shift = card(
        Channel.CENTER,
        recent=ChannelCounts(left=1, center=5, right=2),
        baseline=ChannelCounts(left=7, center=1, right=0),
    )

    assert render_attacking_side_shift(shift) == (
        "More of Barcelona's final-third entries are ending in the center: "
        "5 of the last 8 (63%), up from 1 of 8 (13%) earlier."
    )


def test_a_channel_that_is_not_the_largest_says_which_has_more() -> None:
    shift = card(
        Channel.CENTER,
        recent=ChannelCounts(left=0, center=3, right=5),
        baseline=ChannelCounts(left=5, center=1, right=6),
    )

    assert render_attacking_side_shift(shift) == (
        "More of Barcelona's final-third entries are ending in the center: "
        "3 of the last 8 (38%), up from 1 of 12 (8%) earlier. The right has more: 5."
    )


def test_two_larger_channels_are_both_named() -> None:
    shift = card(
        Channel.CENTER,
        recent=ChannelCounts(left=4, center=3, right=4),
        baseline=ChannelCounts(left=10, center=0, right=10),
    )

    assert render_attacking_side_shift(shift).endswith(
        "earlier. The left (4) and the right (4) have more."
    )


def test_a_team_name_ending_in_s_takes_an_apostrophe_only() -> None:
    shift = replace(
        card(
            Channel.LEFT,
            recent=ChannelCounts(left=6, center=1, right=1),
            baseline=ChannelCounts(left=4, center=4, right=4),
        ),
        team=Team(identifier=TeamId(2), name="Netherlands"),
    )

    assert render_attacking_side_shift(shift).startswith("More of Netherlands' final-third entries")


def burst(recent_shots: int, earlier_shots: int, earlier_seconds: int) -> AttackingBurst:
    return AttackingBurst(
        match_id=MatchId(1),
        team=Team(identifier=TeamId(1), name="Real Madrid"),
        fired_at=MatchClock(period=1, minute=34, second=36),
        trigger_event_id=EventId("shot-1"),
        window_seconds=600,
        earlier_seconds=earlier_seconds,
        recent_shot_ids=tuple(EventId(f"r{index}") for index in range(recent_shots)),
        earlier_shot_ids=tuple(EventId(f"e{index}") for index in range(earlier_shots)),
        recent_entry_ids=(EventId("entry-1"), EventId("entry-2")),
        earlier_entry_ids=(),
        sources=("Synthetic",),
    )


def test_burst_sentence_gives_shots_then_entries_separately() -> None:
    assert render_attacking_burst(burst(4, 3, 24 * 60 + 36)) == (
        "Real Madrid: 4 shots in the last 10 minutes, after 3 in the previous 24 minutes "
        "of play. Final-third entries in the last 10 minutes: 2."
    )


def test_burst_sentence_says_none_when_there_were_no_earlier_shots() -> None:
    assert "after none in the previous 15 minutes" in render_attacking_burst(burst(4, 0, 900))


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
