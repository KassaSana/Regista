# Regista Roadmap

## Vision
A match companion for everyday soccer fans. While a match plays, Regista notices when something meaningful changes, explains it in one plain sentence, and shows the evidence behind it. Quiet when nothing matters.

## Purpose (next 6–12 months)
Learning and portfolio. Free StatsBomb open data is enough. Business questions and paid feeds stay parked until this is revisited on purpose.

## Guiding principles
1. Calculations decide what is interesting; wording comes afterward.
2. Every insight traces to supporting events and sources, from the first insight onward.
3. Sparse beats busy. A quiet match may produce zero cards.
4. Replay before live. Prove the experience on completed matches before paying for data.
5. Provider-specific code stays behind adapters.
6. Observations, not mind-reading: "attacks shifted right," never "the coach ordered."
7. Phases end with evidence, not dates. Each gate asks: what did we learn, and does it justify the next phase?
8. One core, many lenses: a normalized event stream replayed in order. Cards, ratings, and tactical views all read from it.

## Non-goals (for now)
- Computer vision on broadcasts
- Player photos, club crests, league logos
- Betting or prediction features
- A full statistics app competing with FotMob or Sofascore
- Commercial launch on StatsBomb open data (non-commercial license)

---

## Phase 0 — Foundation (done)
Project setup, pitch geometry, typed identifiers, coordinate contract test.

## Phase 1 — First insight on replay (current, locked)
Goal: one detector, end to end, on one match.
Specification: [docs/specs/phase-1-attacking-side-shift.md](docs/specs/phase-1-attacking-side-shift.md)
- Minimal normalized event: identity and ordering, team, period and elapsed time, action type, start and end location, completion status; original record kept alongside.
- Replay engine feeding events in order.
- Attacking-side shift detector, as defined in the specification.
- Template sentence with counts and supporting event identifiers.
- Suppression rule (cooldown).
- Quiet cases produce no card.
- Prefix-invariance test: replay to minute N, alter everything after N; earlier insights must not change.
- Contract tests for channel orientation and completion status.

Exit:
- A synthetic firing case, a quiet case, and a suppression case pass.
- Replaying the real match produces a reviewed golden snapshot. The snapshot is reviewed for correctness, never tuned toward an attractive result. Zero cards is a valid outcome.
- The prefix-invariance test passes.

Human usefulness is judged in Phase 2, not here.

## Phase 2 — Small insight set, evaluation harness, and a minimal replay viewer
- Minimal replay viewer: a timeline, cards, and an evidence view (counts, events, pitch map). Python exports one JSON file per match; a TypeScript + React viewer renders it (see [docs/STACK.md](docs/STACK.md)). Figures for write-ups use `mplsoccer`.
- A script that downloads the chosen StatsBomb matches into `data/` (raw data is never committed; see [DATA_SOURCES.md](DATA_SOURCES.md)). Candidate set: La Liga 2020/21 (35 matches, all with 360 data, all involving Barcelona).
- Development/evaluation match split (10–20 matches); thresholds tuned on development matches only.
- Labeling guide, then hand-labeled noteworthy moments across several matches (owned by me).
- Metrics: precision, cards per match, missed moments.
- Feed field checklist (desk check, no purchase): which fields do the detectors need, and which plausible live feeds provide them?
- Field tilt as a reusable metric (definition in AGENTS.md), used by attacking burst and possibly a later territorial-shift detector.
- Keep open-play and set-piece final-third entry counts separately; detectors use open play only.
- Add attacking burst (shots and final-third entries shown separately) and player involvement (share of team pass attempts while on the pitch).
- Show replays to 5–10 people. Key question: "Which card would have made you look away from the television?"

Gate: is a replayed match worth watching with Regista? If not, fix detection before anything else.

## Phase 3 — Match facts already in the event data
- Cards from recorded formation changes (Tactical Shift), substitutions, and starting lineups.
- Pair them with observed trend changes only as separate, evidenced observations; never claim one caused the other.

Gate: the cards are correct against the event data and are not redundant with Phase 2 cards.

## Phase 4 — Action value
- Heuristic valuer first (the idea from the original rating plan), then a learned possession-value model, both behind the same interface.
- Implement expected threat ourselves as the learning piece. `socceraction` does not install on Python 3.13, so cross-check against it in a throwaway environment (`uv run --python 3.12 --with socceraction ...`). Do not downgrade the project's Python.
- Uses: a "most dangerous spell so far" trigger, and a player explorer showing what drove a performance.
- Write-up: where the heuristic and learned valuers disagree, and which is right.

Gate: the model measurably improves card precision, or the explorer answers questions the cards cannot.

## Phase 5 — Context and provenance layer
- `source_claims` table (subject, predicate, value, dates, source, retrieval time, confidence, license class).
- Point-in-time correctness: context is frozen at kickoff and must have been published before it. Timestamped in-match updates come later and must be added explicitly.
- Wikidata for entities and coach tenures; small hand-curated player context set.
- First context insights (a player returning from a sourced injury, a coach change).

Gate: every context card can answer "how do you know?" instantly.

## Phase 6 — Positional and tactical layer
- SkillCorner open tracking sample and StatsBomb 360 frames for positional experiments. `kloppy` may load them, but only inside an adapter, never in domain code.
- Event-data comparisons with precise definitions: recovery location, directness.
- Defensive line height only from positional data; ball-action locations do not establish where the defensive unit stands.
- Phrase as observed patterns with evidence.

## Optional branches (chosen from what earlier phases teach us)
- Language-model rephrasing of template output, only if people struggle with template wording. Templates stay the source of truth; validation checks entities, numbers, and relationships (who led whom), with template fallback on any failure. "Zero factual errors across the evaluation set" is a release check, not proof of future correctness.
- In-game win probability (needs a team-strength input; evaluate with calibration, log loss, Brier score).
- Manual tagging companion: tag a match while watching and run detectors on the tags.
- Live pilot: verify provider pricing, coverage, and display rights in writing at decision time; measure delivery delay, correction frequency, and card timing; reveal-on-tap by default, no spoiler pushes.
- Sustainability options (parked while the purpose is learning and portfolio): freemium fan product, embeddable insight feed, or niches with direct data access such as college, semi-professional, or youth soccer. Gate: evidence of willingness to pay before building billing.

## Long horizon
Broadcast video understanding (player identification, tracking) only if earlier phases prove the product and a legal footage source exists.

---

## Standing risks
1. Data rights: licenses change or get enforced suddenly. Keep providers swappable, keep terms in writing.
2. Noteworthiness: detection and suppression are the real product, not prose.
3. Trust: one wrong fact breaks the premise.
4. Replay versus live: replay proves engine behavior, not live delivery.
5. Scope creep and planning spirals: finish the current phase before expanding.
6. Share-based detectors favor the team with more of the ball; the team with less possession can be invisible.

## Open questions
- Which matches form the development and evaluation sets?
- What counts as "noteworthy" in labeling? (Write a labeling guide.)
- Which optional branch, if any, earns a place after Phase 4?

## Superseded documents
- The earlier rating-engine plans (`text.md` and `regista_rating_engine_156f9116.plan.md`) were removed. They remain in git history at commit `54422b2`. Their valuation thinking (weight table, possession-value model, positional percentiles) is the starting point for Phase 4.
