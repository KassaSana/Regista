# Regista Roadmap

Last updated: 2026-09-28

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

## Phase 1 — First insight on replay (done, closed 2026-09-27)
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

Result: every exit test passes. The golden snapshot is mechanically verified against an independent recomputation. Kassahun's inspection of the two cards is tracked in the specification.

What we learned:
- The detector is sparse: match 3773497 produces two cards, both for Barcelona.
- Real Madrid, with 30 final-third entries against Barcelona's 96, never reaches the minimums. That confirms standing risk 6: share-based rules favor the team with the ball.
- One card is mostly a move away from a channel rather than toward one. Whether that reads well to a fan is a Phase 2 question.
- One match, one team, cannot tell us whether cards are useful or typical. Phase 2 needs a corpus.

## Phase 2 — Research corpus, exploration, and evaluation (current)
Goal: learn which in-match signals matter to fans, on a corpus large enough to trust, and evaluate detectors honestly.
Specification: [docs/specs/phase-2-data-model.md](docs/specs/phase-2-data-model.md) (data model, corpus, splits)

No machine learning in this phase. First understand the distributions and build simple metrics we can trust.

The largest open uncertainty is fan value, not data engineering. Phase 2 therefore runs as a short loop: a specific fan question, then reproducible analysis, a candidate observation, a replay experience, human judgment, and refinement or rejection. It does not wait for the whole corpus before a fan sees a card.

**Owner sequencing decision (2026-09-27):** proceed with reproducible data acquisition now, deferring the viewing probe. This supersedes the earlier probe-before-bulk-download gate for the first development-data wave. It does not mark the probe complete or establish fan value. Acquire the 266 Premier League development matches and four already-inspected development matches first; keep held-out event files untouched. See [increment 6](docs/increments/06-reproducible-acquisition.md). Subsequent increments still end with a check-in.

Foundations, in order:
1. Catalog of providers, competitions, seasons, and matches, with corpus roles: core breadth (Premier League, La Liga, Serie A, Ligue 1 2015/16; 1,517 matches), modern robustness (recent single-team seasons and tournaments; 377 matches), and a 360 subset kept for Phase 6. **Done (2026-09-27):** `catalog/corpus.toml`; 14 pinned index files verified, covering 1,894 matches in 13 competition-seasons. No bulk event download.
2. Freeze development, validation, and test splits (chronological, about 70/15/15 within each competition-season) from the match index alone, plus a 24-match human-review set drawn from validation. **Done (2026-09-27):** `splits/v1.json` assigns 1,340 development, 279 validation, and 275 test matches, with 24 validation review identifiers. Whole-date inspected exceptions are recorded in the specification. See [increment 5](docs/increments/05-catalog-and-frozen-splits.md).
3. **Fan-value probe 01**, before any bulk download. It is a low-cost usability test (cards read beside a replay), not proof of the final companion experience. Kassahun picks three matches with official full replays, deliberately of different shapes: one dominant performance, one balanced match, and one with a major game-state shift. He records whether he already knew how each match went. They are fetched individually and forced into development. Each gets its side-shift cards plus two or three throwaway prototype observations computed point-in-time: territory up without more threat, a jump in one player's involvement, and a spell that differs from earlier in the match. Kassahun watches with the card timeline and judges every observation. He also notes whether halftime or after the match would have suited it better. Record: `docs/research/probe-01.md`. A clearly negative result redirects the rest of this phase. Status (2026-09-27): sheets generated for Barcelona v Espanyol (2016), Croatia v Brazil and Netherlands v Argentina (World Cup 2022), waiting for Kassahun's viewing.

Data engineering, shaped by what the probe teaches:

4. Reproducible download into `data/` pinned to a provider commit, with a manifest and checksums (raw data is never committed; see [DATA_SOURCES.md](DATA_SOURCES.md)). **First development batch done (2026-09-27):** 270 matches, 931,293 event records, 554 checksummed source files; all verified after acquisition. [Increment 6](docs/increments/06-reproducible-acquisition.md) records commands and integrity checks.
5. Validate every match through the adapter and normalize it into Regista-owned tables. **Done for the first development wave (2026-09-27):** 270 of 270 matches passed validation and every blocking check. See [increment 7](docs/increments/07-validation-and-normalized-warehouse.md).
6. DuckDB analytical tables and data-quality reports. **Done (2026-09-27):** `data/warehouse/regista.duckdb` (development only) rebuilds deterministically. The inventory, quality findings, and owner decisions needed (box-entry definition, field-tilt minimum) are in [increment 8](docs/increments/08-analytical-tables-and-first-wave-audit.md).

Ingestion runs in waves: Premier League 2015/16 first, then the rest of core breadth, then modern robustness. Waves 2 and 3 wait until a specific question needs them.

**Wave 2 (owner request, 2026-09-27):** grow development data for diversity. It added the nine modern-robustness sets and Serie A 2015/16, for 800 development matches from 174 teams, 2015–2024, club and international. There were 0 exclusions, and the rebuild is deterministic. No split change. See [increment 9](docs/increments/09-development-wave-2.md).

**Remote storage (2026-09-27):** private R2 backup and restore (`regista data remote`) is implemented. The real backup and full restore proof passed on 2026-09-27: the restored corpus rebuilt an identical warehouse. See [increment 10](docs/increments/10-remote-storage.md).

**Source backup (2026-09-27):** the code is in a private GitHub repository with a minimal CI workflow (lint, format, strict types, synthetic and unit tests). It is a backup, not a public release.

**Windows portability (2026-09-28):** acquisition and remote restore file operations now run on Windows; the synthetic suite passes there. See [increment 11](docs/increments/11-windows-portability.md).

**Probe data restored (2026-09-28):** the four inspected development matches and pinned indexes are available in the current checkout; the three probe sheets were regenerated from the acquisition pipeline. The owner viewing gate remains pending. See [probe 01](docs/research/probe-01.md).

**Development warehouse restored (2026-09-28):** all 800 development matches were verified and normalized from the pinned source in this checkout; the warehouse contains no held-out matches. See [increment 12](docs/increments/12-development-restoration.md).

Research, on development data only (each piece of research is written up as a research note; see [docs/research/TEMPLATE.md](docs/research/TEMPLATE.md)):

7. Explore the development data. First note (2026-09-27): [research note 05](docs/research/05-territory-and-threat.md), territory versus threat in 10-minute windows. Retrospective; no detector change.
   Follow-up (2026-09-28): [research note 06](docs/research/06-territory-earlier-match.md) compares each spell with earlier play and score state. The association remains modest; no detector change or fan-value claim.
8. Turn fan questions into candidate signals:
   - What changed in the last 10–15 minutes?
   - Who has taken control even though the score has not changed?
   - Is the pressure dangerous or just possession?
   - Which player suddenly became much more involved?
   - Has a team stopped progressing through an area or player that worked earlier?
   - Are chances being created differently than earlier?
   - Did observable behavior change around a substitution or formation change? Report the observations separately, never claim causality.
   - Is this stretch unusual compared with this team's normal behavior? Keep two axes apart and never merge them into one "momentum" score:
     - what an observation is compared with: earlier in this match, this team's prior matches, or league or peer history;
     - what it claims: that something changed, that it is unusual, or that it is threatening.

     "Threatening" is measured from the spell itself (for example its shots, xG, and box entries), never from what happened afterwards.
   - Later: which actions contributed most to a dangerous spell? (This leads into Phase 4.)

   Exploration is expected to kill some detector ideas and produce better ones. What happened after a pattern (for example, shots following a shift) is a legitimate research question and an evaluation target. It never feeds a card shown earlier, and it does not prove the card was useful to a fan.

Detectors and evaluation:

9. Build or refine detectors from what survives the probe and exploration. Candidates carried over:
   - field tilt as a reusable metric (definition in AGENTS.md);
   - attacking burst (shots and final-third entries shown separately);
   - player involvement (share of team pass attempts while on the pitch);
   - separate open-play and set-piece entry counts (detectors use open play only).
10. Evaluate: compare variants on validation, then take one final estimate on test.
    - Correctness: precision, cards per match, missed moments.
    - Experience: timeliness, added understanding, attention cost, repetition across the combined card stream, trust, and whether the person would use Regista for another match.
    - With a handful of judges, the experience measures are reported as counts and quotes, never as percentages.
    - A log of correct but unhelpful cards is kept as deliberately as the good ones. First entry: the 23:11 "shift to the center" card on match 3773497, which is mostly a move away from the right.

Also in this phase:
- Labeling guide, then hand-labeled noteworthy moments on the human-review set (owned by Kassahun).
- Feed field checklist (desk check, no purchase): which fields do the detectors need, and which plausible live feeds provide them? Fields known only in hindsight in the finalized provider data are marked as such (see the Phase 2 specification).
- Once the probe shows the experience is worth building, a minimal replay viewer: a timeline, cards, and an evidence view (counts, events, pitch map). Python exports one JSON file per match; a TypeScript + React viewer renders it (see [docs/STACK.md](docs/STACK.md)). Figures for write-ups use `mplsoccer`. Until then, card timelines come from the command line.
- Show replays to 5–10 people. Key question: "Which card would have made you look away from the television?" If people value the observations at halftime or afterward but not during play, consider changing the usage occasion before adding capabilities.

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
- Follow-up questions about a card ("why was this shown?", "compared with what?", "which players?"). Start with fixed evidence controls; the command-line `--evidence` view is the first. Natural-language questions come only if people repeatedly want more than fixed controls can answer. Structured queries and deterministic calculations would still produce every number, and the model would still not choose which cards appear. This needs an explicit revision of the AGENTS.md rule that a language model may only rephrase templates.
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
4. Replay versus live: replay proves engine behavior, not live delivery. Finalized provider records contain fields known only in hindsight (for example, pass shot-assist flags, carries derived from the next event, and forward links between events). Prefix invariance alone cannot prove a field existed at that moment.
5. Scope creep and planning spirals: finish the current phase before expanding.
6. Share-based detectors favor the team with more of the ball; the team with less possession can be invisible.

## Open questions
- What counts as "noteworthy" in labeling, and how do we label without circularity (marking only what the detector already sees)? (Write a labeling guide.)
- Does any modern robustness set earn a role beyond checking that results still hold on recent football?
- Which optional branch, if any, earns a place after Phase 4?

## Superseded documents
- The earlier rating-engine plans (`text.md` and `regista_rating_engine_156f9116.plan.md`) were removed. They remain in git history at commit `54422b2`. Their valuation thinking (weight table, possession-value model, positional percentiles) is the starting point for Phase 4.
