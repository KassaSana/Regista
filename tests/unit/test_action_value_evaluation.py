"""Check the retrospective action-value ranking calculation."""

from __future__ import annotations

import pytest

from regista.valuation.evaluation import area_under_curve


def test_area_under_curve_handles_ties() -> None:
    assert area_under_curve([0.1, 0.5, 0.5, 0.9], [False, False, True, True]) == pytest.approx(
        0.875
    )
    assert area_under_curve([0.5, 0.5], [False, True]) == pytest.approx(0.5)


def test_area_under_curve_requires_both_outcomes() -> None:
    with pytest.raises(ValueError, match="both positive and negative"):
        area_under_curve([0.1, 0.2], [False, False])
