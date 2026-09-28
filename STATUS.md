# Regista Status

Last updated: 2026-09-28

A short snapshot of where the project stands. [ROADMAP.md](ROADMAP.md) holds the plan; increments and research notes hold the details.

## Tracks (owner decision, 2026-09-28)
- **Product track (current):** a thin MVP. Export a development match, replay it in a viewer, surface a sparse light bulb that opens one insight with its evidence, and review the history after the match. Plan: [increment 20](docs/increments/20-mvp-plan.md).
  | Milestone | State |
  |---|---|
  | M0: record the direction change | done |
  | M1: score in the domain | done |
  | M2: card assembly and export contract | done |
  | M3: viewer skeleton | done |
  | M4: light bulb, insight panel, evidence | next |
  | M5: post-match history, end-to-end check | — |
- **Research track:** Phase 2 first card judgments are in; probe 03 and the gate decision are pending. Phases 3–6 continue only as research; nothing enters the product until promoted.

## Card stream (`uv run regista replay --match <id>`)
| Detector | Fires when | Cards on 800 development matches |
|---|---|---:|
| Attacking side ([spec](docs/specs/phase-1-attacking-side-shift.md)) | At a team's own final-third entry, one channel's share of its last-10-minute entries is at least 25 points above its earlier share | 1,322 |
| Attacking burst ([spec](docs/specs/phase-2-attacking-burst.md)) | At a team's own shot, it has at least 4 non-penalty shots in 10 minutes, at least 3× its earlier rate | 867 |

Combined: 2.74 cards per match (maximum 8), and both teams get a card in 41% of matches. Provisional Phase 3 recorded facts are available with `--facts` and are not part of the stream.

## First judgment (2026-09-28)
All 14 packet cards were judged ([probe 02](docs/research/probe-02.md)):
- **Burst:** 6 of 11 "no", with notes rejecting the rate comparison.
- **Side shift:** 2 yes and 1 maybe of 3.
- **Occasion:** after the match and at stoppages rather than live play.

Product direction recorded: prefer scoreline-against-chance-quality and historically unusual insights over raw counts ([research note 16](docs/research/16-chance-quality-direction.md)). No detector changed yet. [Research note 17](docs/research/17-score-against-chance-quality.md) replays a score-against-chance-quality candidate: it fires in 15% of matches at a 1.0 xG margin, but mostly where the better team also out-shoots its opponent.

## Waiting on Kassahun
0. **Probe 03** ([note](docs/research/probe-03.md)): judge the 12 chance-quality examples in `out/phase2-chance-quality/packet.html` (regenerate with `cd scripts/research && uv run python phase2_chance_quality_packet.py`), then send the exported answers. Open it in a normal browser if possible; the app's preview pane cannot save answers.
1. **Gate decision:** set a pass bar (after the fact, and recorded as such) and decide.
   - Pass: validation comparison.
   - Fail: rework detection.

   Include what to do with the burst card: keep, drop, or rework as "relative to other matches".
2. **Card 8:** why did its evidence not look convincing? The counts reproduce; were the entries just barely into the final third?
3. **Side-shift changes:** review the own-entry timing and wording ([research note 14](docs/research/14-side-shift-timing-and-wording.md)).
4. **Older items** (not blocking): the box-entry definition and field-tilt minimum ([increment 8](docs/increments/08-analytical-tables-and-first-wave-audit.md)), and the clock-anomaly detector response ([research note 04](docs/research/04-provider-clock-and-lineup-anomalies.md)).

## Not started, by design
- **Validation comparison and test estimate:** after the gate passes and variants are frozen.
- **Labeling guide and human-review labels:** needed for precision and missed moments.

## Health
- 334 Python tests pass; Ruff lint and format pass; strict Pyright reports 0 errors.
- Viewer: 15 Vitest tests pass; Biome and strict TypeScript are clean.
- The development warehouse has 800 matches; no held-out match has been opened.
