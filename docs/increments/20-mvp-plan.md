# Increment 20: MVP plan (product track)

Last updated: 2026-09-28

**Status:** M0, M1, and M2 done; M3 next. Owner decision, 2026-09-28: build a thin end-to-end product before finishing every research phase. See the two-track section of [ROADMAP.md](../../ROADMAP.md).

## Context
Phase 2 has produced two working detectors (attacking side shift, attacking burst), a factual stream (lineups, substitutions, formation changes), and a card judgment (probe 02). Probe 03 on chance quality is waiting for your judgment. Until this decision the roadmap blocked any viewer until the Phase 2 gate was decided, and froze Phases 3–6. You have decided to stop finishing research phases in order and build the smallest usable product first:

> "If I open Regista beside a match, does this feel like a real companion product?"

Research continues on a separate track and feeds the product; it no longer blocks it.

**Decisions you made (2026-09-28):**
- **Bulb content:** the side shift is always on. The burst ships labeled "experimental" behind a viewer toggle. Chance quality stays out until probe 03 is judged.
- **Recorded facts:** a quiet context timeline. They never light the bulb.
- **Roadmap:** record the switch to two tracks as your decision. Leakage and split rules stay exactly as they are.

## What already exists (reuse, do not rebuild)
- Replay engine, [domain/replay.py](../../src/regista/domain/replay.py): `replay(events, detector)`. Prefix invariance holds by construction.
- Detectors: `AttackingSideShiftDetector`, `AttackingBurstDetector`, and `RecordedMatchFactsDetector` in [src/regista/detectors/](../../src/regista/detectors/).
- Structured insights, [domain/insights.py](../../src/regista/domain/insights.py): `AttackingSideShift` and `AttackingBurst`. They carry evidence event identifiers and sources.
- Templates, [templates.py](../../src/regista/templates.py): `render_attacking_side_shift`, `render_attacking_burst`, `render_*_evidence`, `render_match_fact`, and `render_clock`.
- Composition root, [cli.py:655](../../src/regista/cli.py:655): already merges both detectors into one replay-ordered stream. This merge logic should become a shared function.
- StatsBomb loading: `load_events` in [adapters/statsbomb/events.py](../../src/regista/adapters/statsbomb/events.py) and `load_match_records` (team names, kickoff) in [adapters/statsbomb/matches.py](../../src/regista/adapters/statsbomb/matches.py).
- The split file `splits/v1.json` and the development-only guard pattern (`require_development` in `pipeline/remote.py`, and `_development_ids` in cli.py).
- The stack is already decided in [docs/STACK.md](../STACK.md): a per-match JSON export with a JSON Schema, TypeScript, Vite, React, hand-written SVG pitch, generated types, Biome, Vitest, and Playwright. Node 26.5.1 is installed (STACK.md corrected in M0).

## What is genuinely missing
1. **The score.** The domain has no goals. `ShotDetail` holds only `penalty`, and own goals map to `OTHER`. The chance-quality script reads the score from `provider_record`, which a product must not do.
2. **Card assembly as a function.** Today the card stream exists only as `print` calls inside `main()`.
3. **The export contract:** `schemas/replay.schema.json` and an exporter.
4. **The viewer** (`viewer/`).
5. **Match selection limited to development matches**, so the product cannot open a validation or test file.

## Minimum user flow
1. `uv run regista export --match <id>` writes `out/exports/<id>.json` (git-ignored). It refuses any match that is not in the development split.
2. `npm run dev` in `viewer/` shows the exported matches. You pick one.
3. **Replay screen:**
   - Header: teams, score, period, and match clock.
   - Controls: play/pause, speed (1×, 10×, 60×), and a scrubber.
   - A small pitch that shows the open card's evidence (the export is thin; see M2).
   - A quiet facts strip for substitutions and formation changes.
4. When a card's trigger time is reached, the **light bulb** lights up quietly (no modal). Clicking it opens **one** insight: the template sentence plus an "evidence" expander. The expander lists the supporting events and marks them on the pitch.
5. At **half-time and full-time**, and at any time through a History tab, a **timeline** shows every surfaced insight so far. Each entry has its clock, the score at that moment, its sentence, and its evidence. It never shows cards later than the current replay position, so it does not spoil the match.
6. "Data: StatsBomb" appears on every screen. The logo is a **placeholder**: you supply the official asset and confirm its usage terms. I will not mark that as done.

## Milestones and acceptance criteria
Every milestone ends with `uv run pytest`, `ruff check`, `ruff format --check`, and `pyright` passing. Once the viewer exists, `npm run check` (Biome, TypeScript, and Vitest) must pass too. I stop and check in with you after each milestone, as AGENTS.md requires.

### M0: Record the direction change (documents only)
- **ROADMAP.md:**
  - Add a "Two tracks (owner, 2026-09-28)" section:
    - **Product track:** export → viewer → bulb → history.
    - **Research track:** probe 03, the gate, validation.
  - Replace "Phases 3–6 frozen" with: "features enter the product only via promotion from research; experimental cards are labeled."
  - Move the viewer out of "Deferred."
- **STATUS.md:** add the product track and the MVP milestone.
- **AGENTS.md:** update scope discipline to "work only on the current milestone of the product track or the active research item."
- **docs/STACK.md:** correct the Node version.
- Add a new increment note, `docs/increments/20-mvp-plan.md`, containing this plan.
- Update "Last updated" everywhere.
- **Accept when:** the documents agree with each other and no leakage or data rule changed.

### M1: Score in the domain
- Extend `ShotDetail` with `outcome_goal: bool`, which is `known_at_event`. Add a way to represent own goals (for example, a `goal_for: Team | None` field set by the adapter from "Own Goal For"), mapped in the StatsBomb adapter.
- Add a pure `ScoreTracker` in `domain/`: it observes events in order and returns the score as it stands after each one.
- Tests:
  - synthetic cases for a goal, an own goal, a penalty goal, and a missed shot;
  - a shootout that is excluded from the score;
  - a contract test giving match 3773497's final score;
  - the existing goldens stay unchanged.
- **Accept when:** the score at every event matches the provider on 3773497, and the prefix-invariance test passes.

### M2: Card assembly and the export contract
- Move the stream-merge logic out of `main()` into one function, for example `regista/product.py: build_card_stream(events) -> list[Card]`. `replay` output keeps using it, and the CLI output must stay byte-identical, as checked against the existing tests and goldens.
- Write `schemas/replay.schema.json` (version 1):
  - `match`: identifier, teams, kickoff date, competition;
  - `attribution`;
  - `timeline`: a compact list per event of identifier, sequence, clock, team, action, location, and score after the event. This is a **thinned** list: no raw provider payloads and no fields beyond what the viewer draws, in line with DATA_SOURCES.md;
  - `cards`: identifier, kind (`side_shift` or `burst`), `experimental`, trigger event and clock, score at trigger, the template sentence, the evidence sentences, the evidence event identifiers, and sources;
  - `facts`: clock and the rendered fact sentence.
- Add the `regista export --match <id> [--output-directory out/exports]` command. It checks `splits/v1.json` and exits with an error for non-development matches.
- Tests:
  - the export validates against the schema (use a stdlib check or a small dev dependency, `jsonschema`, recorded in STACK.md);
  - a synthetic end-to-end export;
  - validation or test match identifiers are refused;
  - a golden export for 3773497 is a derived snapshot, compared locally in the contract tests and never committed as provider data. If the export includes event locations, commit only a hash or the card subset.
- **Accept when:** the exported cards equal the `replay` output for 3773497, and the refusal test passes.

### M3: Viewer skeleton
- Create `viewer/` with Vite, React, and strict TypeScript. Generate types from the schema with `json-schema-to-typescript`. Add Biome and Vitest.
- The Vite dev server serves `../out/exports` so no export is ever copied into `viewer/`.
- Build the match list and the replay screen: header with score and clock, playback controls, and a scrubber.
- Replay-position logic is a pure function, `visibleAt(export, clockPosition)`, which returns the events, score, cards, and facts at or before that position.
- A Vitest test proves that no card or fact appears before its trigger. This is the viewer-side mirror of the prefix rule.
- **Accept when:** you can pick 3773497 and scrub from start to end with the correct score and clock.

### M4: Light bulb, insight panel, and evidence
- Build the bulb component:
  - it is off until a card becomes visible;
  - it has an unread state and opens a panel with one card;
  - if several cards are unread, the panel shows the newest, with a "1 of N" count.
- Build the evidence expander, which highlights the supporting events on the SVG pitch.
- The experimental toggle is off by default and hides burst cards when off. Experimental cards carry an "experimental" label.
- Show the facts strip.
- Put "Data: StatsBomb" with a logo placeholder in the header and inside the panel. The panel needs it too, because a screenshot of the panel can circulate on its own.
- **Accept when:** on 3773497 the bulb lights at each card's trigger clock, the evidence events match the export, and the toggle works.

### M5: Post-match history and an end-to-end check
- Build the History tab and automatic pauses at half-time and full-time, each showing the timeline of surfaced cards so far.
- Add one Playwright test: load 3773497, jump to full time, check that the history holds the expected number of cards, open one card's evidence, and take a screenshot. The screenshot goes in `out/` and is never committed.
- Add the viewer checks to CI with a synthetic export fixture only, never a real one.
- Write a README "Run the MVP" section with three commands.
- **Accept when:** you can run the whole flow on any exported development match. Then you use it on 3–5 matches and write down your impressions. Those impressions are your judgment; I will not invent them.

## Deferred (not in this MVP)
- Chance-quality or scoreline-discrepancy cards: wait for the probe 03 judgment. When promoted, they would describe a "score against chance-quality discrepancy," without claiming a cause such as goalkeeping or finishing.
- Expected threat and action value (Phase 4), context and source claims (Phase 5), and positional work (Phase 6).
- A language model, natural-language follow-up questions, live data, any deployment or public hosting (a public demo requires your license re-check), and accounts.
- Validation and test evaluation, and threshold tuning.

## Guardrails kept
- Detectors are unchanged. The viewer never decides anything; it only reveals what the export contains, by clock.
- Only development matches can be exported, so validation and test stay unopened.
- Exports live in git-ignored `out/`. CI and public tests use synthetic fixtures only.
- No player photos, crests, or logos other than the StatsBomb attribution logo you supply.

## Verification (end to end)
Run these in order:
```bash
uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run pyright
```
```bash
uv run regista export --match 3773497
```
```bash
cd viewer && npm run check && npx playwright test
```
Then run `npm run dev`, open the app in the browser pane, and play 3773497. Confirm three things:
- the bulb lights at the clocks in `tests/golden/3773497-*.json`;
- the score matches the real result;
- the history at full time lists the same cards as `uv run regista replay --match 3773497`.

## Results

### M1: score in the domain (2026-09-28)
- `ShotDetail.scored` (from the shot's own outcome, known at the event) and `Event.own_goal_for` (set only on StatsBomb "Own Goal For", the credited team's record, so each own goal counts once; the same rule the warehouse normalizer already used).
- `regista.domain.score`: `Score`, `ScoreTracker`, and `goal_scored_by`. Period 5 (the shootout) never changes the score.
- The synthetic event builder moved to `tests/support/synthetic_events.py` so domain tests can use it.
- Tests: synthetic goal, miss, penalty goal, own goal, shootout, unknown team, and a prefix check; adapter tests for the goal outcome and own-goal credit; a contract test that match 3773497 ends at its recorded final score.
- Validation: the replayed final score equals the provider's recorded final score in **all 800 development matches** (0 mismatches). A one-off check, not committed; no held-out file was opened.
- Detector output and golden snapshots are unchanged.

### M2: card assembly and the export contract (2026-09-28)
- **Owner decision:** the export is thin and safe for a demo. [DATA_SOURCES.md](../../DATA_SOURCES.md) forbids full event exports in any schema, so the export carries period boundaries, goals with the running score, cards with only their own evidence events, and recorded facts. The viewer's pitch shows the open card's evidence, not all play.
- `regista.product`: `build_card_stream` (moved out of `cli.py`; `replay` output is unchanged) and `build_match_export`. It reads domain events only and never reads the recorded final score. The architecture test allows it the domain, detectors, and templates.
- `schemas/replay.schema.json`, version 1. Side-shift evidence is the recent-window entries; burst evidence is the recent shots plus recent entries. Baseline entries appear only as counts.
- `regista export --match <id>` writes `out/exports/<id>.json` and `index.json`. The split is checked first from identifiers alone, so a validation, test, or unknown match is refused before any provider file is read.
- Development dependencies `jsonschema` and `types-jsonschema`, used in tests only.
- Tests: synthetic product tests (schema, order, experimental flag, score at the trigger with no later goal leaking, evidence ids, the thin-export guard, periods, a quiet match, and a schema rejection); a CLI refusal test; a contract test that match 3773497's export equals the goldens and ends at the recorded score.
- Validation (one-off, not committed):
  - all **800 development exports** validate;
  - cards: 1,322 side shift + 867 burst = 2,189, equal to STATUS;
  - 0 final-score mismatches;
  - each export names 1.0% of the match's events on average (at most 2.6%);
  - match 3773497 exports 4 cards in 33 KB, and a validation match was refused.
