"""Ranking measure for retrospective comparisons of action-value methods."""

from __future__ import annotations


def area_under_curve(scores: list[float], targets: list[bool]) -> float:
    """Mann-Whitney area with average ranks for tied scores."""
    positives = sum(targets)
    negatives = len(targets) - positives
    if not positives or not negatives:
        raise ValueError("area under curve needs both positive and negative examples")
    ordered = sorted(zip(scores, targets, strict=True))
    positive_rank_sum = 0.0
    position = 0
    while position < len(ordered):
        following = position + 1
        while following < len(ordered) and ordered[following][0] == ordered[position][0]:
            following += 1
        average_rank = (position + following + 1) / 2
        positive_rank_sum += average_rank * sum(target for _, target in ordered[position:following])
        position = following
    return (positive_rank_sum - positives * (positives + 1) / 2) / (positives * negatives)
