"""Firing, quiet, suppression, and edge cases for the attacking burst detector.

Timelines start period 1 at 0:00. The default window is 10 minutes, at least 4
recent shots are needed, the recent rate must be at least 3 times the earlier
rate, and there must be at least 10 minutes of earlier play.
"""

from fractions import Fraction

from synthetic_events import AWAY, HOME, SOURCE, EventStream

from regista.detectors.attacking_burst import AttackingBurstDetector, BurstSettings
from regista.domain.entries import Channel
from regista.domain.events import MatchClock
from regista.domain.insights import AttackingBurst
from regista.domain.replay import replay


def run(stream: EventStream, settings: BurstSettings | None = None) -> list[AttackingBurst]:
    return list(replay(stream.events, AttackingBurstDetector(settings)))


def started() -> EventStream:
    stream = EventStream()
    stream.other(HOME, 1, 0)
    return stream


def test_a_burst_fires_once_at_the_shot_that_completes_it() -> None:
    stream = started()
    earlier = stream.shot(HOME, 1, 5)
    earlier_entry = stream.entry(HOME, 1, 6, 0, Channel.LEFT)
    recent_entry = stream.entry(HOME, 1, 20, 0, Channel.RIGHT)
    recent = [stream.shot(HOME, 1, minute) for minute in (21, 23, 25, 27)]

    cards = run(stream)

    assert len(cards) == 1
    card = cards[0]
    assert card.team == HOME
    assert card.fired_at == MatchClock(1, 27, 0)
    assert card.trigger_event_id == recent[-1].identifier
    assert card.recent_shot_ids == tuple(shot.identifier for shot in recent)
    assert card.earlier_shot_ids == (earlier.identifier,)
    assert card.recent_entry_ids == (recent_entry.identifier,)
    assert card.earlier_entry_ids == (earlier_entry.identifier,)
    # The window starts at 17:00, so 17 minutes of earlier play.
    assert (card.window_seconds, card.earlier_seconds) == (600, 17 * 60)
    assert card.sources == (SOURCE,)


def test_a_steady_shot_rate_stays_quiet() -> None:
    stream = started()
    for index in range(1, 17):
        stream.shot(HOME, 1, *divmod(150 * index, 60))

    assert run(stream) == []


def test_a_second_burst_inside_the_cooldown_is_suppressed() -> None:
    stream = started()
    for minute in (21, 23, 25, 27, 28, 29, 30, 31):
        stream.shot(HOME, 1, minute)

    assert [card.fired_at for card in run(stream)] == [MatchClock(1, 27, 0)]


def test_the_team_fires_again_once_the_cooldown_ends() -> None:
    stream = started()
    for minute in (21, 23, 25, 27, 33, 34, 35, 36, 37):
        stream.shot(HOME, 1, minute)

    # The cooldown ends at 37:00. The window then holds 5 shots (33:00-37:00)
    # against 4 in 27 earlier minutes: 5/600 is at least 3 x 4/1620.
    assert [card.fired_at for card in run(stream)] == [MatchClock(1, 27, 0), MatchClock(1, 37, 0)]


def test_penalties_do_not_count() -> None:
    stream = started()
    for minute in (21, 23, 25):
        stream.shot(HOME, 1, minute)
    stream.shot(HOME, 1, 27, penalty=True)

    assert run(stream) == []


def test_the_other_teams_shots_neither_count_nor_trigger() -> None:
    stream = started()
    for minute in (21, 23, 25):
        stream.shot(HOME, 1, minute)
    stream.shot(AWAY, 1, 26)
    stream.shot(AWAY, 1, 27)

    assert run(stream) == []


def test_there_must_be_ten_minutes_of_earlier_play() -> None:
    stream = started()
    for minute in (11, 12, 13, 14, 19, 19):
        stream.shot(HOME, 1, minute)

    # At 14:00 only 4 minutes precede the window; at 19:00 there are 9.
    assert run(stream) == []


def test_the_window_never_reaches_into_the_previous_period() -> None:
    stream = started()
    for minute in (40, 42, 44, 46):
        stream.shot(HOME, 1, minute, 30)
    stream.other(HOME, 2, 45)
    stream.shot(HOME, 2, 55, 0)

    # Period 1's shots at 40:30-46:30 fire a card there. On the continuous clock
    # they fall inside 45:00-55:00, but in period 2 they count as earlier play.
    assert [card.fired_at for card in run(stream)] == [MatchClock(1, 46, 30)]


def test_a_rate_ratio_exactly_at_the_threshold_fires() -> None:
    stream = started()
    stream.shot(HOME, 1, 2)
    stream.shot(HOME, 1, 4)
    for minute in (21, 23, 25, 27):
        stream.shot(HOME, 1, minute)

    # 4 shots in 600 s against 2 in 1020 s is a rate ratio of exactly 3.4.
    assert [card.fired_at for card in run(stream)] == [MatchClock(1, 27, 0)]
    exact = BurstSettings(minimum_rate_ratio=Fraction(4 * 1020, 2 * 600))
    assert [card.fired_at for card in run(stream, exact)] == [MatchClock(1, 27, 0)]
    above = BurstSettings(minimum_rate_ratio=Fraction(4 * 1020, 2 * 600) + Fraction(1, 1000))
    assert run(stream, above) == []
