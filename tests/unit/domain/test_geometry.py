"""Properties of Regista's provider-independent pitch geometry."""

from dataclasses import FrozenInstanceError
from math import pi

import pytest
from hypothesis import given
from hypothesis import strategies as st

from regista.domain.geometry import Pitch, Point

pitch_coordinate = st.floats(
    min_value=0.0,
    max_value=120.0,
    allow_nan=False,
    allow_infinity=False,
)
half_width_offset = st.floats(
    min_value=0.0,
    max_value=40.0,
    allow_nan=False,
    allow_infinity=False,
)


def test_point_is_an_immutable_value_object() -> None:
    point = Point(x=60.0, y=40.0)

    with pytest.raises(FrozenInstanceError):
        point.x = 61.0  # type: ignore[misc]


def test_standard_pitch_uses_verified_coordinate_frame() -> None:
    pitch = Pitch()

    assert pitch.length == 120.0
    assert pitch.width == 80.0
    assert pitch.opponent_goal_center == Point(x=120.0, y=40.0)


def test_distance_uses_the_opponent_goal_center() -> None:
    pitch = Pitch()

    assert pitch.distance_to_opponent_goal(Point(x=120.0, y=40.0)) == 0.0
    assert pitch.distance_to_opponent_goal(Point(x=0.0, y=40.0)) == 120.0


def test_angle_is_zero_on_the_central_axis() -> None:
    assert Pitch().angle_to_opponent_goal(Point(x=60.0, y=40.0)) == 0.0


def test_geometry_rejects_locations_outside_the_pitch() -> None:
    pitch = Pitch()

    with pytest.raises(ValueError, match="outside the pitch"):
        pitch.distance_to_opponent_goal(Point(x=121.0, y=40.0))


@given(x=pitch_coordinate, offset=half_width_offset)
def test_distance_and_angle_are_symmetric_about_the_center_line(
    x: float,
    offset: float,
) -> None:
    pitch = Pitch()
    left = Point(x=x, y=pitch.width / 2.0 - offset)
    right = Point(x=x, y=pitch.width / 2.0 + offset)

    assert pitch.distance_to_opponent_goal(left) == pytest.approx(
        pitch.distance_to_opponent_goal(right)
    )
    assert pitch.angle_to_opponent_goal(left) == pytest.approx(pitch.angle_to_opponent_goal(right))


@given(x=pitch_coordinate, offset=half_width_offset)
def test_angle_is_an_unsigned_deviation_from_the_goal_axis(
    x: float,
    offset: float,
) -> None:
    angle = Pitch().angle_to_opponent_goal(Point(x=x, y=40.0 + offset))

    assert 0.0 <= angle <= pi / 2.0
