"""Render one StatsBomb match's shot locations as a dependency-free SVG."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from html import escape
from pathlib import Path
from typing import TypedDict, cast

SCALE = 10
MARGIN = 30


class NamedObject(TypedDict):
    name: str


class RawEvent(TypedDict, total=False):
    location: list[float]
    minute: int
    period: int
    team: NamedObject
    type: NamedObject


def _line(x1: float, y1: float, x2: float, y2: float) -> str:
    return (
        f'<line x1="{MARGIN + x1 * SCALE}" y1="{MARGIN + y1 * SCALE}" '
        f'x2="{MARGIN + x2 * SCALE}" y2="{MARGIN + y2 * SCALE}" />'
    )


def render(events: Sequence[RawEvent]) -> str:
    """Return an SVG pitch containing every shot in an event sequence."""
    width = 120 * SCALE
    height = 80 * SCALE
    shots = [event for event in events if event.get("type", {}).get("name") == "Shot"]
    teams = sorted({event.get("team", {}).get("name", "Unknown") for event in shots})
    colors = dict(zip(teams, ("#2563eb", "#dc2626"), strict=False))
    pitch_lines = [
        f'<rect x="{MARGIN}" y="{MARGIN}" width="{width}" height="{height}" />',
        _line(60, 0, 60, 80),
        _line(18, 18, 18, 62),
        _line(0, 18, 18, 18),
        _line(0, 62, 18, 62),
        _line(102, 18, 102, 62),
        _line(102, 18, 120, 18),
        _line(102, 62, 120, 62),
        f'<circle cx="{MARGIN + 60 * SCALE}" cy="{MARGIN + 40 * SCALE}" r="100" />',
    ]
    markers: list[str] = []
    for event in shots:
        location = event.get("location")
        if location is None or len(location) != 2:
            continue
        team = event.get("team", {}).get("name", "Unknown")
        title = escape(
            f"{team}, period {event.get('period', '?')}, minute {event.get('minute', '?')}"
        )
        markers.append(
            f'<circle class="shot" cx="{MARGIN + location[0] * SCALE}" '
            f'cy="{MARGIN + location[1] * SCALE}" r="7" fill="{colors[team]}">'
            f"<title>{title}</title></circle>"
        )
    legend = " · ".join(f"{team}: {colors[team]}" for team in teams)
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width + 2 * MARGIN} '
            f'{height + 2 * MARGIN + 35}" role="img" aria-labelledby="title description">',
            '<title id="title">Shot locations for StatsBomb match 3773497</title>',
            '<desc id="description">'
            "Both teams attack from x equals zero toward x equals 120."
            "</desc>",
            "<style>",
            "rect,line,circle:not(.shot){fill:none;stroke:#475569;stroke-width:2}",
            ".shot{stroke:#fff;stroke-width:2;opacity:.85}",
            "text{font:18px sans-serif;fill:#0f172a}",
            "</style>",
            '<rect x="0" y="0" width="100%" height="100%" fill="#f8fafc" />',
            *pitch_lines,
            f'<text x="{MARGIN}" y="{height + 2 * MARGIN + 20}">{escape(legend)}</text>',
            *markers,
            "</svg>",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.events.open(encoding="utf-8") as event_file:
        events = cast(list[RawEvent], json.load(event_file))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(events), encoding="utf-8")


if __name__ == "__main__":
    main()
