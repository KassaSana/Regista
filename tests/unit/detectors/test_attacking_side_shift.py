"""Firing, quiet, suppression, and edge cases for the attacking-side shift detector.

Timelines use a 12-entry baseline between 0:00 and 7:20 and recent entries one
per minute from 11:00. The baseline only reaches 12 once all of it has left the
10-minute window (after 17:20), so the eighth recent entry at 18:00 is the
first moment both minimums can hold.
"""

from fractions import Fraction

from synthetic_events import (
    HOME,
    SOURCE,
    EventStream,
    add_balanced_baseline,
    add_baseline,
    add_recent,
)

from regista.detectors.attacking_side_shift import AttackingSideShiftDetector
from regista.domain.entries import Channel
from regista.domain.events import MatchClock
from regista.domain.insights import AttackingSideShift, ChannelCounts
from regista.domain.replay import replay

LEFT, CENTER, RIGHT = Channel.LEFT, Channel.CENTER, Channel.RIGHT
LEFT_SHIFT = [LEFT, LEFT, CENTER, LEFT, LEFT, RIGHT, LEFT, LEFT]


def run(stream: EventStream) -> list[AttackingSideShift]:
    return list(replay(stream.events, AttackingSideShiftDetector()))


def test_a_clear_shift_fires_exactly_one_card_with_its_evidence() -> None:
    stream = EventStream()
    baseline = add_balanced_baseline(stream)
    recent = add_recent(stream, LEFT_SHIFT)

    cards = run(stream)

    assert len(cards) == 1
    card = cards[0]
    assert card.team == HOME
    assert card.channel is LEFT
    assert card.fired_at == MatchClock(1, 18, 0)
    assert card.trigger_event_id == recent[-1].identifier
    assert card.recent == ChannelCounts(left=6, center=1, right=1)
    assert card.baseline == ChannelCounts(left=4, center=4, right=4)
    assert card.share_increase == Fraction(6, 8) - Fraction(1, 3)
    assert card.recent_entry_ids == tuple(event.identifier for event in recent)
    assert card.baseline_entry_ids == tuple(event.identifier for event in baseline)
    assert card.channels_losing_share == (CENTER, RIGHT)
    assert card.sources == (SOURCE,)


def test_balanced_entries_stay_quiet() -> None:
    stream = EventStream()
    add_balanced_baseline(stream)
    add_recent(stream, [LEFT, CENTER, RIGHT, LEFT, CENTER, RIGHT, LEFT, CENTER])
    stream.other(HOME, 1, 30)

    assert run(stream) == []


def test_a_second_shift_inside_the_cooldown_is_suppressed_and_fires_after_it() -> None:
    stream = EventStream()
    add_balanced_baseline(stream)
    add_recent(stream, LEFT_SHIFT)
    # The first card fires at 18:00. Entries then swing right, whatever the channel.
    add_recent(stream, [RIGHT] * 9, first_minute=19)
    during_cooldown = run(stream)
    stream.entry(HOME, 1, 28, 0, RIGHT)

    after_cooldown = run(stream)

    assert [card.fired_at for card in during_cooldown] == [MatchClock(1, 18, 0)]
    assert [(card.fired_at, card.channel) for card in after_cooldown] == [
        (MatchClock(1, 18, 0), LEFT),
        (MatchClock(1, 28, 0), RIGHT),
    ]


def test_too_few_recent_entries_produce_no_card() -> None:
    stream = EventStream()
    add_balanced_baseline(stream)
    add_recent(stream, [LEFT] * 7)
    stream.other(HOME, 1, 18)

    assert run(stream) == []


def test_too_small_a_baseline_produces_no_card() -> None:
    stream = EventStream()
    add_baseline(stream, [LEFT, CENTER, RIGHT] * 3 + [CENTER, RIGHT])
    add_recent(stream, [LEFT] * 8)

    assert run(stream) == []


def test_nothing_fires_in_the_first_ten_minutes_of_a_period() -> None:
    stream = EventStream()
    add_balanced_baseline(stream)
    stream.other(HOME, 1, 47)
    stream.other(HOME, 2, 45)  # the period starts at 45:00 (a Half Start event)
    add_recent(stream, [LEFT] * 8, period=2, first_minute=46)
    stream.other(HOME, 2, 54, 59)
    before_ten_minutes = run(stream)
    stream.other(HOME, 2, 55)

    cards = run(stream)

    assert before_ten_minutes == []
    assert [card.fired_at for card in cards] == [MatchClock(2, 55, 0)]


def test_the_window_never_includes_the_previous_periods_stoppage_time() -> None:
    stream = EventStream()
    add_balanced_baseline(stream)
    # Seven first-half stoppage-time entries at minutes 45-46 of period 1. On the
    # continuous clock they fall inside 45:00-55:00, but they belong to period 1.
    for second in range(0, 105, 15):
        stream.entry(HOME, 1, 45 + second // 60, second % 60, LEFT)
    stream.other(HOME, 1, 47)
    stream.other(HOME, 2, 45)
    stream.entry(HOME, 2, 54, 0, LEFT)
    stream.other(HOME, 2, 55)

    assert run(stream) == []


def test_the_cooldown_does_not_carry_into_the_next_period() -> None:
    stream = EventStream()
    add_balanced_baseline(stream)
    add_recent(stream, [LEFT] * 8, first_minute=39)  # fires at 46:00, period 1
    stream.other(HOME, 1, 47)
    stream.other(HOME, 2, 45)  # the period starts at 45:00 (a Half Start event)
    add_recent(stream, [LEFT] * 8, period=2, first_minute=46)
    stream.other(HOME, 2, 55)  # before 56:00, when a carried-over cooldown would end

    cards = run(stream)

    assert [card.fired_at for card in cards] == [MatchClock(1, 46, 0), MatchClock(2, 55, 0)]


def test_a_shift_made_only_of_set_pieces_produces_no_card() -> None:
    stream = EventStream()
    add_balanced_baseline(stream)
    add_recent(stream, [LEFT] * 8, open_play=False)

    assert run(stream) == []


def test_an_increase_split_across_two_channels_below_the_threshold_produces_no_card() -> None:
    stream = EventStream()
    add_baseline(stream, [LEFT] * 2 + [CENTER] * 8 + [RIGHT] * 2)
    # Left and right each rise from 1/6 to 3/8 (about 21 points): neither reaches 25.
    add_recent(stream, [CENTER, CENTER, LEFT, RIGHT, LEFT, RIGHT, LEFT, RIGHT])

    assert run(stream) == []


def test_the_largest_increase_is_reported_and_losing_channels_are_evidence() -> None:
    stream = EventStream()
    add_baseline(stream, [LEFT] + [CENTER] * 10 + [RIGHT])
    add_recent(stream, [RIGHT, LEFT, RIGHT, LEFT, RIGHT, LEFT, LEFT, CENTER])

    cards = run(stream)

    assert [card.channel for card in cards] == [LEFT]
    assert cards[0].recent == ChannelCounts(left=4, center=1, right=3)
    assert cards[0].channels_losing_share == (CENTER,)


def test_equal_increases_are_broken_in_left_center_right_order() -> None:
    stream = EventStream()
    add_baseline(stream, [LEFT] + [CENTER] * 10 + [RIGHT])
    add_recent(stream, [RIGHT, LEFT] * 4)

    assert [card.channel for card in run(stream)] == [LEFT]


def test_incomplete_passes_do_not_count_as_entries() -> None:
    stream = EventStream()
    add_balanced_baseline(stream)
    for minute in range(11, 19):
        stream.entry(HOME, 1, minute, 0, LEFT, completed=False)

    assert run(stream) == []
