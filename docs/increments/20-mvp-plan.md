# Increment 20: MVP plan (product track)

Last updated: 2026-09-28

**Status:** MVP complete (M0–M5 done, 2026-09-28). Owner decision, 2026-09-28: build a thin end-to-end product before finishing every research phase. See the two-track section of [ROADMAP.md](../../ROADMAP.md).

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

### M3: viewer skeleton (2026-09-28)
- `viewer/`: Vite 8, React 19, strict TypeScript 6, Biome, Vitest. No router, state library, or UI kit. The generated `src/replayTypes.ts` comes from the schema (`npm run types`).
- A development-only Vite plugin serves `out/exports` at `/exports` and rejects anything outside that directory. A build copies no export.
- `src/replay.ts` (pure): recorded periods are laid end to end as one replay position, because the provider minute overlaps at half time. `visibleAt` reveals goals, cards, and facts only at or after their own clock; the score is the last visible goal's.
- Screens: a match list from `index.json`; a match screen with the scoreboard, period and clock, play/pause at 1×, 10×, or 60×, a scrubber with period markers, goals and changes so far, and "Data: StatsBomb" with a logo placeholder (the owner supplies the logo).
- Tests (synthetic fixture with a goal in each half-time overlap): every second round-trips across half time; no goal, card, or fact is visible one second before its clock, and each is visible at it; the score at each moment; clamping; labels.
- Checked in the browser on match 3773497:
  - 0–0 at kickoff; 0–0 at 12:57 and 1–0 at 12:58; 2–0 at half time (47:22); the clock jumps 47:22 → 45:01; 2–0 at 59:08 and 2–1 at 59:09;
  - playback at 60× stops at 94:06 on 2–1;
  - no horizontal scroll at 375 px, and no console errors;
  - path-traversal probes did not reach files outside `out/exports`.

### M4: light bulb, insight panel, and evidence (2026-09-28)
- `insights.ts` (pure):
  - `shownCards` works on cards already visible at the replay position, so the prefix rule carries over;
  - experimental cards stay hidden unless the toggle is on;
  - `bulbOf` gives off, new (with a count), or seen, and the card a click opens.
- **Bulb:** in the clock row. It is quiet: one soft pulse when new, no sound, no modal, and the pulse is off under reduced motion.
- **Panel:** one insight inline, so play continues. It shows:
  - the kind, plus an Experimental badge when flagged;
  - the clock, the team, and the score **when it fired**;
  - the sentence;
  - Earlier/Later through the cards surfaced so far;
  - "Data: StatsBomb" inside the panel.

  Opening a card marks it read. Scrubbing back hides later cards again but keeps them read.
- **"Why this insight?":** an SVG pitch in the acting team's attacking frame with the final-third line, plus channel lines on side-shift cards. Entries are arrows and shots are dots. The evidence table sits below it, then the sources.
- **Experimental toggle:** "Show experimental insights" is off by default and kept in `localStorage` (guarded). Turning it off closes an open burst card.
- **Tests:** 7 new Vitest tests (22 in total):
  - the bulb is off before each card's clock and new at it;
  - the toggle hides the burst;
  - seen and new transitions, and scrubbing back;
  - each card keeps its own score.
- **Checked in the browser on match 3773497:**
  - off at 24:13, and 1 new insight at 24:14;
  - the Barcelona side-shift card at 1–0 has 11 arrows and both channel lines;
  - with the toggle off, the 34:36 burst does not light the bulb;
  - with the toggle on it lights at exactly 34:36, carries the Experimental badge at 2–0, and has 4 shot dots and 4 entry arrows;
  - at full time, 2 new insights, and stepping walks all 4 in order;
  - no page overflow at 375 px, and the bulb sits below the team names (measured).
- **Layout fixes made during the check:** the bulb collided with the away name at 375 px, and the evidence table wrapped. The bulb moved into the clock row, and the table now scrolls inside its box.
- **Known limit:** the browser pane cropped phone-size screenshots, so the phone check rests on DOM measurements.

### M5: breaks, history, end-to-end check, and CI (2026-09-28)
- **Breaks:** playback stops exactly at every period end. `breakBetween` in `replay.ts` is tested; resuming from a break never stops again. At half time and full time the screen switches to "Insights so far" with a summary (the break and the score), and Continue resumes play.
- **History:** a tab with every insight surfaced so far, in match order. Each entry shows its clock, the score then, the sentence, and "Why this insight?". It never lists a later card, and it counts hidden experimental insights without showing them. Viewing it marks those insights seen. A match with no card says "Nothing stood out so far. Regista stays quiet when nothing matters."
- **Playback timing:** playback now runs on a wall-clock timer instead of animation frames. Browsers stop animation frames in hidden tabs, which froze the replay whenever the viewer was not in the foreground, and a companion often sits in a background tab.
- **Export:** `regista export` accepts repeated `--match`. One held-out match refuses the whole request, and no event file is read (tested).
- **End-to-end test:** Playwright (`npm run e2e`) runs on a synthetic export served through `REGISTA_EXPORTS_DIR`, on its own port, with the installed Chrome. It covers:
  - picking a match;
  - the bulb off, then lit at the card's second;
  - the panel and its pitch evidence;
  - the half-time stop, the summary, and Continue;
  - the experimental reveal;
  - the full-time stop and the history;
  - scrubbing back hiding later insights;
  - no console errors;
  - a second, quiet case.
- **Favicon:** an inline icon, because the browser's automatic `/favicon.ico` request was a 404 on every page.
- **CI:** a `viewer` job checks that the generated types match the schema, then runs `npm run check` and `npm run e2e`, on synthetic data only.
- **Checked in the browser on real development exports:**
  - match 3773497 stops at half time (47:22) at 2–0 with 1 insight, plus a note of 1 hidden experimental insight;
  - Continue resumes the second half;
  - it stops at full time (94:06) at 2–1 with 2 insights and no Continue;
  - match 3802683 (Paris Saint-Germain v AS Monaco, no cards) never lights the bulb, and its history says so.

## MVP summary
What it does:
1. Export development matches.
2. Pick one in the viewer.
3. Play or scrub with the correct score, clock, goals, and changes.
4. A quiet light bulb lights only when an insight surfaces, and it opens one insight with its evidence on a pitch.
5. Playback pauses at breaks with everything noticed so far.
6. The history can be read at any moment, without spoilers.

The side shift is on by default; the burst is experimental and hidden by default.

Deferred:
- chance-quality cards (probe 03);
- the Phase 2 gate and its validation and test estimates;
- the Phase 3–6 research content;
- a language model;
- live data;
- any deployment or public hosting (it needs the logo and a license re-check).

Owner items: see "Waiting on Kassahun" in [STATUS.md](../../STATUS.md).
