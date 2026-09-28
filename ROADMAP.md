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

## Product direction (owner, 2026-09-28)
- Prefer insights a fan would not get from the broadcast or the scoreboard. Raw volume ("4 shots in 10 minutes") is usually too obvious unless context makes it unusual.
- The most interesting signal is disagreement between visible outcomes and underlying performance: a scoreline that hides chance quality, finishing or goalkeeping far from what similar chances normally produce, and spells that are unusual against historical matches.
- Live, Regista is a sparse light bulb that opens to one insight. Cards stay available at breaks in play and after the match.
- Wording stays factual ("the scoreline doesn't reflect the difference in chance quality so far"), never "should be winning".

This is direction, not a commitment to build. See [research note 16](docs/research/16-chance-quality-direction.md).

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
Specifications: [data model, corpus, and splits](docs/specs/phase-2-data-model.md); [attacking burst](docs/specs/phase-2-attacking-burst.md). Current state and open owner items: [STATUS.md](STATUS.md).

No machine learning in this phase. First understand the distributions and build simple metrics we can trust. The largest open uncertainty is fan value, not data engineering.

**Owner decisions on sequencing (2026-09-27/28):**
- Reproducible acquisition went ahead before any viewing probe.
- Full-match viewing was declined. Automated development-only audits are proxies for signal quality, never owner judgments of fan usefulness.
- A cross-provider comparison needs matched matches, compatible definitions, and a separately frozen corpus before it can support a claim.

**Scope freeze (2026-09-28):** no new Phase 3–6 work until the Phase 2 gate below is decided. Existing provisional work in those phases stays as it is, unused by the default card stream except where noted.

### Done
1. Catalog: `catalog/corpus.toml`, 1,894 matches in 13 competition-seasons ([increment 5](docs/increments/05-catalog-and-frozen-splits.md)).
2. Frozen splits `splits/v1.json`: 1,340 development, 279 validation, 275 test, plus a 24-match human-review set drawn from validation.
3. Reproducible acquisition and validation of 800 development matches, 174 teams, 2015–2024 ([increments 6](docs/increments/06-reproducible-acquisition.md)–[9](docs/increments/09-development-wave-2.md), [12](docs/increments/12-development-restoration.md)). No held-out event file has been opened.
4. The development DuckDB warehouse with analytical tables and data-quality reports ([increment 8](docs/increments/08-analytical-tables-and-first-wave-audit.md)), private R2 backup with a proven restore ([increment 10](docs/increments/10-remote-storage.md)), and Windows portability ([increment 11](docs/increments/11-windows-portability.md)).
5. Exploration notes, all on development data only:
   - territory and threat: [05](docs/research/05-territory-and-threat.md) and [06](docs/research/06-territory-earlier-match.md);
   - side-shift audits: [12](docs/research/12-side-shift-automated-audit.md) and [13](docs/research/13-side-shift-flagged-cards.md);
   - side-shift timing and wording variants: [14](docs/research/14-side-shift-timing-and-wording.md);
   - the second detector: [15](docs/research/15-second-detector-attacking-burst.md).
6. Detector refinement ([increment 19](docs/increments/19-phase2-gate-readiness.md)):
   - The side shift now fires only at the team's own entry, with neutral wording.
   - The attacking burst was added as a second card type, because the side shift alone covers 8% of low-volume team performances.
   - `regista replay` shows both detectors in one stream.
7. The fan-value method was replaced with a card-judging packet: [probe 02](docs/research/probe-02.md). The earlier full-match probe is [probe 01](docs/research/probe-01.md).
8. First packet judged (2026-09-28, all 14 cards):
   - Burst: 6 of 11 "no".
   - Side shift: 2 yes and 1 maybe of 3.
   - Occasion: after the match and at stoppages, not live play.
   - Gate decision pending: no pass bar was set before judging.
9. Chance quality against the scoreline was sized as the next candidate direction: [research note 16](docs/research/16-chance-quality-direction.md).
10. Score against chance quality, replayed at every shot ([research note 17](docs/research/17-score-against-chance-quality.md)): at a 1.0 xG margin it fires in 122 of 800 matches, but only 12 of 166 candidates have comparable shot counts. The next step is a small owner packet before any detector.
11. [Probe 03](docs/research/probe-03.md): a pre-registered 12-example chance-quality packet (more shots, similar volume, one dominant chance, finishing or goalkeeping). Awaiting owner judgment.

### Fan questions that guide the research
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

What happened after a pattern is a legitimate research question and evaluation target. It never feeds a card shown earlier, and it does not prove the card was useful to a fan.

### Gate (revised 2026-09-28)
Question: does Regista's card stream tell a fan something worth opening during play, or after the match, that the broadcast would not already have told them?

Method: [probe 02](docs/research/probe-02.md), a 14-card judging packet from five development matches. It is framed around the owner's proposed experience: during play, a small light-bulb indicator that opens to the insight; every card available after the match.
1. Kassahun records a pass bar in probe 02 **before** opening the packet.
2. Kassahun judges the packet and exports the answers.
3. The answers are transferred verbatim, and the decision follows the pass bar:
   - **Pass:** freeze the detector variants, compare them on validation (correctness, cards per match, timeliness), then take one final estimate on test. Build a viewer only if the pass shows during-play value worth prototyping.
   - **Fail:** fix detection before anything else. If both card types are judged obvious, the next candidates are the owner's "relative to other matches" comparison (baselines from earlier kickoffs only) and, by explicit owner decision, lifting the scope freeze for tactical content (recorded formation changes, Phase 3).

Known limits of this method: it cannot measure missed moments, live timing against the broadcast, or attention cost while watching. They stay open, not passed.

### Deferred until the gate is decided
- Labeling guide and hand-labeled noteworthy moments on the human-review set (owned by Kassahun); needed to measure precision and missed moments on validation.
- Feed field checklist (desk check, no purchase).
- The minimal replay viewer (see [docs/STACK.md](docs/STACK.md)) and showing replays to 5–10 people. The key question becomes: "Which light bulb would you have opened?"
- More detector candidates: field tilt (needs an owner-set minimum), player involvement, separate set-piece entry counts.
- Log of correct but unhelpful cards. First entry: the match 3773497 "center" card (now 24:14), which is mostly a move away from the right.

## Phase 3 — Match facts already in the event data
*Frozen until the Phase 2 gate is decided (2026-09-28).*
- Development-only inventory (2026-09-28): [research note 07](docs/research/07-recorded-match-facts.md) found 1,600 starting lineups, 5,384 substitutions, and 743 recorded formation changes across 800 matches. A separate factual replay stream is justified provisionally; fan value and combined-stream redundancy remain unjudged.
- Provisional implementation (2026-09-28): [recorded-fact specification](docs/specs/phase-3-recorded-match-facts.md) and [increment 13](docs/increments/13-recorded-match-facts.md) add `replay --facts`. All 800 development event files replayed with the expected fact counts. The default Phase 2 card feed is unchanged.
- Cards from recorded formation changes (Tactical Shift), substitutions, and starting lineups.
- Pair them with observed trend changes only as separate, evidenced observations; never claim one caused the other.

Gate: the cards are correct against the event data and are not redundant with Phase 2 cards.

## Phase 4 — Action value
*Frozen until the Phase 2 gate is decided (2026-09-28).*
- Provisional research foundation (2026-09-28): a provider-neutral action-value contract, geometric movement baseline, development-only expected-threat trainer, and synthetic equation cross-check are implemented. The full-development fitted grid is a retrospective research artifact and cannot support leakage-free replay claims for its training matches. A strict date-cutoff option supplies an earlier-trained surface for research; deployment-time provenance checks remain. See [research note 08](docs/research/08-expected-threat-foundation.md).
- Chronological development check (2026-09-28): a surface trained on 673 pre-2023 development matches was compared on 127 later development matches. It did not improve end-location shot/goal ranking over the geometric heuristic on this proxy. No detector promotion follows; see [research note 09](docs/research/09-expected-threat-later-matches.md).
- Heuristic valuer first (the idea from the original rating plan), then a learned possession-value model, both behind the same interface.
- Implement expected threat ourselves as the learning piece. `socceraction` does not install on Python 3.13, so cross-check against it in a throwaway environment (`uv run --python 3.12 --with socceraction ...`). Do not downgrade the project's Python.
- Uses: a "most dangerous spell so far" trigger, and a player explorer showing what drove a performance.
- Write-up: where the heuristic and learned valuers disagree, and which is right.

Gate: the model measurably improves card precision, or the explorer answers questions the cards cannot.

## Phase 5 — Context and provenance layer
*Frozen until the Phase 2 gate is decided (2026-09-28).*
- Provisional infrastructure (2026-09-28): an append-only source-claim DuckDB store and immutable kickoff snapshot enforce publication, retrieval, and store-recording cutoffs plus validity dates. It contains no curated real-world claims or context cards. See the [source-claim specification](docs/specs/phase-5-source-claims.md) and [increment 16](docs/increments/16-source-claim-store.md).
- Read-only Wikidata research adapter (2026-09-28): a bounded team-QID query returns unreviewed head-coach tenure candidates with statement links, optional references, and date precision. It does not populate `source_claims`; live endpoint validation and owner source review remain. See [research note 10](docs/research/10-wikidata-coach-candidates.md).
- `source_claims` table (subject, predicate, value, dates, source, retrieval time, confidence, license class).
- Point-in-time correctness: context is frozen at kickoff and must have been published before it. Timestamped in-match updates come later and must be added explicitly.
- Wikidata for entities and coach tenures; small hand-curated player context set.
- First context insights (a player returning from a sourced injury, a coach change).

Gate: every context card can answer "how do you know?" instantly.

## Phase 6 — Positional and tactical layer
*Frozen until the Phase 2 gate is decided (2026-09-28).*
- Event-data baseline (2026-09-28): development-only recovery-location and completed-movement directness definitions covered all 1,600 team-matches. They are retrospective ball-action descriptors, not defensive-line estimates or tactical cards. See [research note 11](docs/research/11-event-data-recovery-and-directness.md).
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
6. Share-based detectors favor the team with more of the ball; the team with less possession can be invisible. (At corpus scale: the side shift covers 8% of the lowest entry-volume quartile; research note 15.)
7. Obviousness: a correct card that repeats what the broadcast or the fan's own eyes already said has little value (owner concern, 2026-09-28).

## Open questions
- Usage occasion: the owner proposed (2026-09-28) a light-bulb indicator during play that opens to one insight, with the full card list after the match. Which content earns the indicator, and does anything earn it during play rather than afterwards? Probe 02 asks per card.
- What counts as "noteworthy" in labeling, and how do we label without circularity (marking only what the detector already sees)? (Write a labeling guide.)
- Does any modern robustness set earn a role beyond checking that results still hold on recent football?
- Which optional branch, if any, earns a place after Phase 4?

## Superseded documents
- The earlier rating-engine plans (`text.md` and `regista_rating_engine_156f9116.plan.md`) were removed. They remain in git history at commit `54422b2`. Their valuation thinking (weight table, possession-value model, positional percentiles) is the starting point for Phase 4.
