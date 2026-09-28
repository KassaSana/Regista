"""Build the probe 03 chance-quality judging packet from development matches only.

Run: ``uv run python scripts/research/phase2_chance_quality_packet.py``.
Sampling follows the rules pre-registered in ``docs/research/probe-03.md``:
note 17 candidates, four mutually exclusive categories, three matches per
category drawn with a fixed seed, and a shuffled display order that hides the
category. Writes ``out/phase2-chance-quality/packet.html`` and
``selection.json`` (git-ignored). Nothing in the packet is a judgment.
"""

from __future__ import annotations

import html
import json
import random
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from math import sqrt

from phase2_card_audit import ROOT, development_event_files, development_ids
from phase2_chance_quality import Candidate, replay_match, shot_outcome, shot_xg, type_name
from phase2_judging_packet import (
    SCRIPT,
    STYLE,
    MatchInfo,
    match_metadata,
    question_fieldsets,
)

from regista.adapters.statsbomb.events import load_events
from regista.domain.events import ActionType, Event
from regista.domain.ids import MatchId
from regista.pipeline.catalog import load_corpus

SEED = 2026092803
OUTPUT = ROOT / "out/phase2-chance-quality"
PROBE_TWO_MATCHES = frozenset({3754020, 3879570, 3773656, 3939984, 3920416})
NOTE_17_EXAMPLES = frozenset({3754013, 3878552, 3879743})
PER_CATEGORY = 3
CATEGORY_ORDER = ("D", "C", "B", "A")
CATEGORY_NAMES = {
    "D": "finishing or goalkeeping distorts the score",
    "C": "one dominant chance",
    "B": "similar volume, different quality",
    "A": "more shots and better chances",
}
PERIOD_NAMES = {1: "first half", 2: "second half", 3: "extra time, first", 4: "extra time, second"}
OUTCOME_CLASSES = {"Goal": "goal", "Saved": "saved", "Saved to Post": "saved"}


@dataclass(frozen=True, slots=True)
class Shot:
    """One shot as known at the candidate moment."""

    team: str
    xg: float
    outcome: str
    x: float
    y: float
    penalty: bool


@dataclass(frozen=True, slots=True)
class Moment:
    """Everything the packet shows for one candidate, rebuilt from its prefix."""

    candidate: Candidate
    shots: tuple[Shot, ...]
    goals: dict[str, int]

    def team_shots(self, team: str, *, penalty: bool) -> list[Shot]:
        return [shot for shot in self.shots if shot.team == team and shot.penalty is penalty]

    def xg(self, team: str) -> float:
        return sum(shot.xg for shot in self.team_shots(team, penalty=False))

    def non_penalty_goals(self, team: str) -> int:
        return sum(shot.outcome == "Goal" for shot in self.team_shots(team, penalty=False))


def _moment(candidate: Candidate, events: list[Event]) -> Moment:
    shots: list[Shot] = []
    goals: Counter[str] = Counter()
    for event in events:
        if event.sequence > candidate.trigger_sequence:
            break
        if event.action is ActionType.SHOT and event.shot is not None:
            outcome = shot_outcome(event) or "Unknown"
            location = event.location
            shots.append(
                Shot(
                    team=event.team.name,
                    xg=shot_xg(event),
                    outcome=outcome,
                    x=0.0 if location is None else location.x,
                    y=0.0 if location is None else location.y,
                    penalty=event.shot.penalty,
                )
            )
            goals[event.team.name] += outcome == "Goal"
        elif type_name(event) == "Own Goal For":
            goals[event.team.name] += 1
    moment = Moment(candidate, tuple(shots), dict(goals))
    # The rebuilt moment must agree with the note 17 candidate exactly.
    team, other = candidate.team, candidate.opponent
    if (goals[team], goals[other]) != (candidate.goals_for, candidate.goals_against):
        raise ValueError(f"score differs from candidate in match {candidate.match_id}")
    if (round(moment.xg(team), 2), round(moment.xg(other), 2)) != (
        candidate.xg_for,
        candidate.xg_against,
    ):
        raise ValueError(f"xG differs from candidate in match {candidate.match_id}")
    counts = (
        len(moment.team_shots(team, penalty=False)),
        len(moment.team_shots(other, penalty=False)),
    )
    if counts != (candidate.shots_for, candidate.shots_against):
        raise ValueError(f"shot counts differ from candidate in match {candidate.match_id}")
    return moment


def category(moment: Moment) -> str | None:
    """Assign the pre-registered category, in precedence order D, C, B, A."""
    c = moment.candidate
    if c.goals_for < c.goals_against and (
        moment.non_penalty_goals(c.opponent) - moment.xg(c.opponent) >= 1.0
    ):
        return "D"
    if c.largest_shot_share > 0.5:
        return "C"
    ratio = c.shots_for / c.shots_against if c.shots_against else float("inf")
    if 0.8 <= ratio <= 1.25:
        return "B"
    if ratio >= 1.5:
        return "A"
    return None


def _pools() -> tuple[dict[float, list[Moment]], dict[int, MatchInfo]]:
    files = development_event_files(development_ids())
    excluded = (
        set(load_corpus(ROOT / "catalog/corpus.toml").inspected_match_ids)
        | PROBE_TWO_MATCHES
        | NOTE_17_EXAMPLES
    )
    pools: dict[float, list[Moment]] = {1.0: [], 0.75: []}
    for match_id, path in sorted(files.items()):
        if match_id in excluded:
            continue
        events = load_events(path, MatchId(match_id))
        for margin in pools:
            pools[margin] += [_moment(c, events) for c in replay_match(match_id, events, margin)]
    return pools, match_metadata()


def _draw(
    pools: dict[float, list[Moment]], generator: random.Random
) -> list[tuple[str, float, Moment]]:
    chosen: list[tuple[str, float, Moment]] = []
    used: set[int] = set()
    for label in CATEGORY_ORDER:
        taken = 0
        for margin in (1.0, 0.75):
            earliest: dict[int, Moment] = {}
            for moment in pools[margin]:
                c = moment.candidate
                if category(moment) == label and c.match_id not in used:
                    earliest.setdefault(c.match_id, moment)
            matches = sorted(earliest)
            generator.shuffle(matches)
            for match_id in matches[: PER_CATEGORY - taken]:
                chosen.append((label, margin, earliest[match_id]))
                used.add(match_id)
                taken += 1
            if taken == PER_CATEGORY:
                break
    return chosen


def _strip(moment: Moment, team: str) -> str:
    """Every chance as a dot on a 0-1 xG axis; stacked when values are close."""
    width, left = 300, 8
    dots: list[str] = []
    stacks: Counter[int] = Counter()
    for shot in sorted(moment.team_shots(team, penalty=False), key=lambda item: item.xg):
        column = int(min(shot.xg, 1.0) * 40)
        level = stacks[column]
        stacks[column] += 1
        cx = left + min(shot.xg, 1.0) * (width - 2 * left)
        cy = 40 - level * 9
        kind = OUTCOME_CLASSES.get(shot.outcome, "miss")
        dots.append(f'<circle cx="{cx:.1f}" cy="{cy}" r="4" class="{kind}"/>')
    ticks = "".join(
        f'<line x1="{left + t * (width - 2 * left)}" y1="46" x2="{left + t * (width - 2 * left)}" '
        f'y2="50" class="axis"/><text x="{left + t * (width - 2 * left)}" y="60" '
        f'class="tick">{t:g}</text>'
        for t in (0, 0.25, 0.5, 0.75, 1)
    )
    top = 30 - 9 * max(stacks.values(), default=1)
    return (
        f'<svg viewBox="0 {top} {width} {64 - top}" class="strip" role="img" '
        f'aria-label="{html.escape(team)} chance values">'
        f'<line x1="{left}" y1="46" x2="{width - left}" y2="46" class="axis"/>{ticks}'
        f"{''.join(dots)}</svg>"
    )


def _shot_map(moment: Moment, team: str) -> str:
    """The attacking half in the team's own frame: goal at the right, its left at the top."""
    scale = 3
    marks: list[str] = []
    for shot in moment.team_shots(team, penalty=False) + moment.team_shots(team, penalty=True):
        cx, cy = (shot.x - 60) * scale, shot.y * scale
        radius = 3 + 10 * sqrt(shot.xg)
        kind = OUTCOME_CLASSES.get(shot.outcome, "miss")
        if shot.penalty:
            marks.append(
                f'<rect x="{cx - radius}" y="{cy - radius}" width="{2 * radius}" '
                f'height="{2 * radius}" class="{kind}"/>'
            )
        else:
            marks.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" class="{kind}"/>')
    return (
        f'<svg viewBox="-4 -4 {60 * scale + 8} {80 * scale + 8}" class="halfpitch" role="img" '
        f'aria-label="{html.escape(team)} shot map">'
        f'<rect x="0" y="0" width="{60 * scale}" height="{80 * scale}" class="turf"/>'
        f'<rect x="{42 * scale}" y="{18 * scale}" width="{18 * scale}" height="{44 * scale}" '
        f'class="box"/><rect x="{54 * scale}" y="{30 * scale}" width="{6 * scale}" '
        f'height="{20 * scale}" class="box"/>{"".join(marks)}</svg>'
    )


def _team_block(moment: Moment, team: str) -> str:
    shots = moment.team_shots(team, penalty=False)
    penalties = moment.team_shots(team, penalty=True)
    xg = moment.xg(team)
    values = ", ".join(
        f"{shot.xg:.2f}{' (goal)' if shot.outcome == 'Goal' else ''}"
        for shot in sorted(shots, key=lambda item: -item.xg)
    )
    penalty_text = (
        "none"
        if not penalties
        else f"{len(penalties)} ({sum(p.outcome == 'Goal' for p in penalties)} scored, "
        f"{sum(p.xg for p in penalties):.2f} xG)"
    )
    per_shot = f"{xg / len(shots):.2f}" if shots else "–"
    return (
        f'<div class="team"><h3>{html.escape(team)}</h3>'
        f"<table><tr><td>shots (no penalties)</td><td>{len(shots)}</td></tr>"
        f"<tr><td>expected goals (no penalties)</td><td>{xg:.2f}</td></tr>"
        f"<tr><td>expected goals per shot</td><td>{per_shot}</td></tr>"
        f"<tr><td>goals, not counting penalties</td><td>{moment.non_penalty_goals(team)}</td></tr>"
        f"<tr><td>penalties</td><td>{penalty_text}</td></tr></table>"
        f"{_strip(moment, team)}"
        f'<p class="values">Chance values, largest first: {values or "none"}</p>'
        f"{_shot_map(moment, team)}</div>"
    )


def _sentence(c: Candidate) -> str:
    state = (
        f"trail {c.goals_for}–{c.goals_against}"
        if c.goals_for < c.goals_against
        else f"are level at {c.goals_for}–{c.goals_against}"
    )
    return (
        f"{c.team} {state}, but have created the better chances: {c.xg_for:.2f} expected goals "
        f"to {c.xg_against:.2f} (StatsBomb's chance-quality model, penalties excluded)."
    )


QUESTIONS = [
    (
        "supported",
        "Is the statement factually supported by what is shown?",
        ["Yes", "No", "Can't tell"],
    ),
    ("interesting", "Is it interesting?", ["Yes", "Somewhat", "No"]),
    (
        "obvious",
        "Would you have understood this from the score and basic shot count alone?",
        ["Yes", "Partly", "No"],
    ),
    (
        "when",
        "When would it be most useful?",
        ["Live", "At halftime or a stoppage", "After the match", "Not useful"],
    ),
    (
        "outlier",
        "Does one chance or a penalty make the summary misleading?",
        ["Yes", "No", "Not sure"],
    ),
]

EXTRA_STYLE = """
.teams{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:640px){.teams{grid-template-columns:1fr}}
.team h3{margin:8px 0 4px;font-size:1rem}.strip{width:100%;height:auto}
.halfpitch{width:60%;max-width:200px;height:auto;display:block;margin-top:6px}
.axis{stroke:var(--muted)}.tick{font-size:9px;fill:var(--muted);text-anchor:middle}
circle.goal,rect.goal{fill:var(--accent)}circle.saved,rect.saved{fill:var(--recent)}
circle.miss,rect.miss{fill:none;stroke:var(--earlier);stroke-width:1.5}
.values{font-size:.85rem;color:var(--muted);margin:4px 0}
"""


def build() -> dict[str, object]:
    pools, matches = _pools()
    generator = random.Random(SEED)
    chosen = _draw(pools, generator)
    uncategorized = sum(1 for moment in pools[1.0] if category(moment) is None)
    generator.shuffle(chosen)
    sections: list[str] = []
    selection: list[dict[str, object]] = []
    for number, (label, margin, moment) in enumerate(chosen, start=1):
        c = moment.candidate
        info = matches[c.match_id]
        example_id = f"{c.match_id}:{c.trigger_sequence}"
        period = PERIOD_NAMES.get(c.period, f"period {c.period}")
        home_goals, away_goals = moment.goals.get(info.home, 0), moment.goals.get(info.away, 0)
        score = f"{info.home} {home_goals}–{away_goals} {info.away}"
        teams = _team_block(moment, c.team) + _team_block(moment, c.opponent)
        sections.append(
            f'<article class="card" data-card="{example_id}"><header>'
            f'<span class="num">Example {number}</span><span class="clock">'
            f"{c.minute:02d}:{c.second:02d} · {period}</span>"
            f'<span class="score">{html.escape(score)}</span></header>'
            f'<p class="meta">{html.escape(info.competition)} {html.escape(info.season)} · '
            f"{html.escape(info.date)}</p>"
            f'<p class="sentence">{html.escape(_sentence(c))}</p>'
            f'<div class="teams">{teams}</div>'
            '<p class="legend">Strip: each dot is one shot placed by its expected-goals value '
            "(0 = almost never scored, 1 = almost always). Filled red: goal. Filled blue: saved. "
            "Hollow: blocked, off target, or post. Map: attacking half, goal on the right, dot "
            "size by chance value; squares are penalties.</p>"
            f'<div class="judge">{question_fieldsets(example_id, QUESTIONS)}'
            f'<label class="note">Note<textarea name="{example_id}.note" rows="2"></textarea>'
            "</label></div></article>"
        )
        selection.append(
            {
                "example": number,
                "category": label,
                "category_name": CATEGORY_NAMES[label],
                "margin": margin,
                "match_id": c.match_id,
                "trigger_sequence": c.trigger_sequence,
                "clock": f"{c.minute:02d}:{c.second:02d}",
                "team": c.team,
                "xg": f"{c.xg_for} to {c.xg_against}",
                "shots": f"{c.shots_for} to {c.shots_against}",
            }
        )
    packet = sha256(json.dumps(selection, sort_keys=True).encode()).hexdigest()[:12]
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Regista chance quality</title><style>{STYLE}{EXTRA_STYLE}</style></head>"
        f'<body data-packet="{packet}"><main><h1>Regista chance quality</h1>'
        f'<p class="sub">Packet {packet} · {len(chosen)} examples from development matches · '
        "private working file, do not circulate</p>"
        "<p>Each example is one moment in a match where a team that is not winning has "
        "created better chances. Everything shown was known at that moment; the final result "
        "is not shown. Judge each example on its own. Press Export answers at the end and send "
        "the text back.</p>"
        f"{''.join(sections)}<h2>Overall</h2>"
        '<label class="note">Which kind of example, if any, felt like a real Regista insight? '
        'Why?<textarea name="overall.note" rows="4"></textarea></label>'
        '<p><button id="make-export" type="button">Export answers</button></p>'
        '<textarea id="export" readonly aria-label="Exported answers"></textarea>'
        "<footer>Data: StatsBomb. Chance values are StatsBomb's expected-goals model, from "
        "StatsBomb Open Data used for non-commercial research.</footer>"
        f"</main><script>{SCRIPT}</script></body></html>"
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "packet.html").write_text(page, encoding="utf-8")
    summary: dict[str, object] = {
        "packet": packet,
        "seed": SEED,
        "pool_at_margin_1": len(pools[1.0]),
        "pool_by_category_at_margin_1": dict(
            sorted(Counter(str(category(m)) for m in pools[1.0]).items())
        ),
        "uncategorized_at_margin_1": uncategorized,
        "examples": selection,
    }
    (OUTPUT / "selection.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
