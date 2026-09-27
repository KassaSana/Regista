# Phase 2 Specification: Data Model and Research Corpus

Last updated: 2026-09-27

**Status: catalog, frozen splits, first development acquisition, validation, the normalized and analytical development warehouse, and data-quality reporting implemented (increments 5–8). The held-out warehouse and `team_window_distributions` remain design.**
Increments [7](../increments/07-validation-and-normalized-warehouse.md) and [8](../increments/08-analytical-tables-and-first-wave-audit.md) record the warehouse, its inventory, and the deviations noted in this document.
Increment 5 acquired and verified the pinned match indexes and created `splits/v1.json`.
The probe's owner judgments remain pending. On 2026-09-27 the owner authorized starting reproducible acquisition before viewing, superseding that sequencing gate for the first development wave. See the [catalog execution record](../increments/05-catalog-and-frozen-splits.md) and [acquisition increment](../increments/06-reproducible-acquisition.md).
Change this specification deliberately and record why.

## Goals
- Hundreds to thousands of matches, from more than one provider eventually, with no provider-specific tables past the adapter.
- Reproducible: any table can be rebuilt from pinned raw files, and every row can say where it came from.
- Honest evaluation: splits are frozen before anyone looks at the data, and whole-match numbers can never leak into an in-match detector.
- Enough structure to explore, no more. Most provider detail stays queryable but unmodeled until a question needs it.

## Pipeline order
1. **Catalog.** Record what exists and what we use (`catalog/corpus.toml`).
2. **Freeze splits.** This needs only the match index (dates and identifiers), never event content (`splits/v1.json`).
3. **Fan-value probe 01.** Three matches Kassahun can rewatch, fetched individually and forced into development, with side-shift cards and a few point-in-time prototype observations judged by Kassahun (see ROADMAP.md). The result decides which fields and questions the steps below prioritize.
4. **Download and manifest.** Pinned, checksummed raw files in `data/raw/`.
5. **Validate and normalize.** Every match goes through the adapter into Regista tables.
6. **Build analytical tables and data-quality reports** in DuckDB.
7. **Explore development data only.**
8. **Identify useful signals and questions.** Exploration is expected to kill some detector ideas.
9. **Build and refine detectors.**
10. **Evaluate on validation, then once on test.**

There is no machine learning in Phase 2. First we understand the distributions and build simple metrics we can trust.

## Research corpus
Match counts were verified against the provider's match indexes on 2026-09-27.

| Role | Competition-seasons | Matches | Coverage |
|---|---|---:|---|
| Core breadth | Premier League 2015/16 (380), La Liga 2015/16 (380), Serie A 2015/16 (380), Ligue 1 2015/16 (377 of 380) | 1,517 | Complete season (Ligue 1 has 3 gaps) |
| Modern robustness | Bundesliga 2023/24 (34, Leverkusen only), Ligue 1 2021/22 (26) and 2022/23 (32), mostly Paris Saint-Germain, La Liga 2020/21 (35, Barcelona only), World Cup 2022 (64), Euro 2020 (51), Euro 2024 (51), Copa América 2024 (32), AFCON 2023 (52) | 377 | Single team or tournament |
| Excluded for now | Bundesliga 2015/16 (34 of 306, Leverkusen only), MLS 2023 (6), La Liga 2004/05–2019/20 (Barcelona only) | — | — |
| 360 subset | Flagged in the catalog wherever 360 frames exist (most modern sets). Frames are not downloaded until Phase 6. | — | — |

- **Coverage** is recorded per competition-season: `complete_season`, `single_team`, or `tournament`. "Is this unusual for this team?" baselines only make sense for teams with complete seasons. A single-team set only tells us about that team and its opponents on the day.
- **Known anomalies** are recorded in the catalog and checked by data quality: one Serie A 2015/16 match and one Ligue 1 2015/16 match have no `data_version` metadata, and Ligue 1 2015/16 is missing 3 matches.
- **Ingestion waves:**
  1. Premier League 2015/16 (380 matches, about 1.3 GB of event JSON).
  2. The rest of core breadth.
  3. Modern robustness.

  The design must handle every wave; the waves exist so each stage is proven on well-understood data first.

  **As run (2026-09-27):** wave 1 ingested the 266 Premier League development matches plus the 4 inspected matches. At the owner's request, a diversity-first wave 2 then added every development match of the nine modern-robustness sets and Serie A 2015/16, for 800 development matches ([increment 9](../increments/09-development-wave-2.md)). The remaining La Liga and Ligue 1 2015/16 development matches are still cataloged but not yet acquired.

## Layer 1: Raw (local only, immutable)
Provider files exactly as downloaded. Never committed (see [DATA_SOURCES.md](../../DATA_SOURCES.md)).

- **Layout:** `data/raw/statsbomb-open-data/<source_commit>/data/...`, mirroring the provider's repository paths (`competitions.json`, `matches/<competition>/<season>.json`, `events/<match>.json`, `lineups/<match>.json`).
- **Pinning:** downloads use a specific `hudl/open-data` commit, never `master`, so a rebuild months later gets byte-identical inputs. A newer provider release lands in a new commit directory; old ones are never edited.
- **Manifest:** `data/raw/manifest.jsonl`, append-only, one line per file, loaded into the `raw_files` table.

| Field | Meaning |
|---|---|
| `provider`, `dataset` | `statsbomb`, `open-data` |
| `source_commit`, `url`, `relative_path` | Where the file came from and where it lives |
| `kind` | `competitions`, `matches`, `events`, `lineups`, or `three_sixty` |
| `provider_match_id` | For match-level files |
| `sha256`, `bytes` | Checked again whenever the file is read |
| `retrieved_at` | When we downloaded it |
| `provider_last_updated` | The provider's `last_updated` for that match, from the match index |
| `license_class` | For example `statsbomb-public-data-agreement` (non-commercial) |

## Layer 2: Normalized (Regista-owned tables)
Two DuckDB files, both never committed, with the same schemas (`normalized` and `analytical`):
- `data/warehouse/regista.duckdb` holds **development matches only**. Research tools, including the read-only DuckDB server configured for agents, point here.
- `data/warehouse/held_out.duckdb` holds validation and test matches. Only evaluation code opens it.

Read-only access alone does not protect held-out matches: a read-only connection can still read any file. Keeping held-out matches in a file research tools never open makes the protection structural. Once the development warehouse exists, research connections also switch off DuckDB's access to outside files (`SET enable_external_access = false`), so raw files for held-out matches cannot be read through them either. An agent with shell access can still read any file, so for agents the rule in AGENTS.md remains the final safeguard.

**Conventions for every table:**
- Rows carry `provider` plus the provider's own identifiers. A Regista-wide identity across providers (the same match from two providers) is deferred until a second provider exists. That is a recorded decision at that time, not now.
- Every row carries `ingest_run_id`, pointing at the run and code version that produced it.
- **Space:** Regista's frame is 120 by 80, and the acting team always attacks toward increasing x. Each adapter converts into it (StatsBomb already matches). Low y is the acting team's left.
- **Time:** `period`, `period_seconds` (from the provider's period-relative timestamp, to the millisecond), and the provider's `minute` and `second`. The continuous minute overlaps across periods, so no calculation may use it without the period.
- **Availability:** every normalized field is tagged in the schema documentation with when it becomes known:
  - `known_at_event`: known when the event happens (for example the location of a pass, or its outcome).
  - `delayed`: known once the following event arrives (for example a carry, which the provider builds from the next action). Replay may use it, but a live pilot must measure the delay.
  - `hindsight`: known only after later events or post-match processing (for example pass shot-assist and goal-assist flags, `play_pattern`, possession grouping, and forward links in `related_events`).

  Detectors may read only `known_at_event` and `delayed` fields. `hindsight` fields are for retrospective research only. Until a contract test shows otherwise, a field whose timing is unclear counts as `hindsight`.

| Table | Contents |
|---|---|
| `ingest_runs` | Run ID; Regista version and git commit; adapter version; source commit; start and finish times; status |
| `competition_seasons` | Provider identifiers and names, gender, role, coverage, expected and present match counts |
| `matches` | Date, local kickoff time, home and away team, final score, match week, stage, stadium, provider `data_version`, `xy_fidelity_version`, `shot_fidelity_version`, provider last-updated time, 360 availability, raw file checksums, data-quality status |
| `teams`, `players` | Identifiers and names only. No photos, crests, or logos. |
| `appearances` | Per match and player: team, jersey number, whether they started |
| `position_spells` | Each position a player held: position, start and end (period and seconds), start and end reasons |
| `events` (the spine) | Match, event ID, sequence, time, team, player, possession number and possession team (`hindsight` until shown otherwise), Regista `event_type`, `provider_event_type`, x and y, end x and y (for moving actions), `under_pressure`, and `provider_record` (the full original record as JSON) |
| `passes` | Recipient, completed, set-piece type (empty means open play), height, cross, shot assist and goal assist (both `hindsight`) |
| `carries` | Event key only; the end location lives in `events` |
| `shots` | xG (**the provider's model**, labeled as such), outcome, goal, shot type (open play, free kick, penalty, corner), body part, key-pass event |
| `substitutions` | Player off, player on, reason |
| `formation_changes` | Team and formation, from Starting XI and Tactical Shift events |
| `goals` | Scoring team and kind (shot or own goal), derived from shots and own-goal events |

**Regista event types:** pass, carry, shot, pressure, duel, dribble, ball recovery, interception, clearance, block, foul, goalkeeper, substitution, formation change, period start, period end, other. Each adapter maps its provider's types onto these. An unknown provider type fails loudly, as open-play pass types already do.

### How much normalization before exploration?
Normalize the spine, plus exactly what the questions below need. Leave the rest in `provider_record` JSON, which DuckDB can still query. A field moves from JSON into a table only when a question needs it, and every promotion comes with a contract test pinning the provider assumption.

| Question fans care about | Needs |
|---|---|
| What changed in the last 10–15 minutes? | Event spine and time |
| Who has taken control even though the score hasn't changed? | Possession, passes by zone, goals, score state |
| Is the pressure dangerous, or just possession? | Shots and xG, final-third and box entries, possessions |
| Which player suddenly became much more involved? | Player on events, time on the pitch |
| Has a team stopped progressing through an area or player that worked earlier? | Pass recipient, start and end locations, carries |
| Are chances being created differently than earlier? | Shots, shot type, key pass, location |
| Did behavior change around a substitution or formation change? (Observations only, never cause) | Substitutions, formation changes, position spells |
| Is this stretch unusual for this team? | Team summaries from strictly earlier matches |
| Later: which actions drove a dangerous spell? | Possessions and action value (Phase 4) |

## Layer 3: Analytical (derived Regista tables)
Schema `analytical`, rebuilt deterministically from `normalized`. Every table records a `definition_version`, so a changed definition (for example of a final-third entry) is visible, not silent.

| Table | Contents |
|---|---|
| `final_third_entries` | Every entry under the locked AGENTS.md definition, with channel |
| `score_states` | Home and away score before every event |
| `player_intervals` | When each player was on the pitch |
| `team_time_bins` | Per match, team, period, and 5-minute bin: passes, completed passes, entries by channel, completed open-play passes starting at x ≥ 80 (field tilt numerator), shots, xG, pressures, recoveries |
| `possessions` | Team, start, end, duration, furthest x, reached the final third, ended in a shot, xG |
| `team_match_summary` | Per-match team totals, for exploration and data-quality checks. Never a baseline for how unusual a spell is. |
| `team_window_distributions` | For each team, the distribution of a metric over windows of a given length in its earlier matches. This is the only source for "unusual for this team" claims. |
| `dq_checks` | One row per match and check: status and detail |

**As implemented (2026-09-27).**
- The layer also has `team_matches`, `periods`, `event_context` (a wide event table with zones, open play, xG, and score state), `box_entries`, `player_period_spans`, `player_match_involvement`, `player_time_bins`, and `definitions`.
- `dq_checks` lives in `normalized`, because quality is decided before the analytical layer is built.
- `box_entries` uses a **provisional definition v1**, awaiting owner review: an open-play completed pass or carry from outside to inside the penalty area (x ≥ 102, 18 ≤ y ≤ 62).
- `team_time_bins.field_tilt` applies no minimum count yet.
- `player_intervals` takes the union of position spells, cut at the player's Substitution event when the lineup runs past it.
- `team_window_distributions` is deferred until a research note chooses a metric and a window.

**Leakage rules for this layer:**
- Analytical tables summarize whole matches. Exploration reads them from the development warehouse, which contains development matches only.
- In-match detectors never read analytical tables for the match being replayed. They see only the replay stream.
- "Normal for this team" baselines use only matches with a kickoff strictly before the current one, matching the context rule in AGENTS.md.
- A whole-match average cannot say how rare a 10-minute spell is. A historical comparison compares a window with windows of the same length in earlier matches. It states its sample size and eligibility rules, and never treats overlapping windows as independent observations. When the sample is too small, the historical claim is left out; within-match comparisons still stand without it.
- Observations keep two axes separate, and are never merged into one "momentum" score:
  - **Comparison:** earlier in this match, this team's prior matches, or league or peer history. Only the first needs no history; the others state their sample and eligibility.
  - **Claim:** changed, unusual, or threatening. A threat claim uses what happened inside the spell (shots, xG, box entries), known at the event. What followed the spell is an evaluation target only.

### Detector outcomes
Every time a detector checks a team, the outcome is one of three, and replay output and evaluation count them separately:
- **card**: the rule fired;
- **no change**: there was enough data, and nothing met the rule;
- **insufficient data**: the minimums were not met, so the detector cannot tell. On match 3773497, Real Madrid's silence is this outcome, not "no change".

The Phase 1 detector and its `No cards.` output predate this distinction. They change when the probe or the first Phase 2 detector needs it.

### Data-quality checks
These are mechanical checks, not soccer content, so running them on every match does not break the split.
- The event file checksum matches the manifest.
- Both teams are present, and the event count is plausible.
- `sequence` is unique, strictly increasing, and has no gaps.
- The clock never runs backwards within a period.
- All coordinates lie on the pitch.
- No provider type is unknown (the check fails loudly).
- Lineups and substitutions agree: every substitute who comes on appears in the lineup.
- The final score in the match index equals the goals derived from events, excluding penalty shootouts (period 5).
- Provider metadata (`data_version` and fidelity versions) is present.

Results go to `dq_checks`, with a readable summary in `out/dq/` (git-ignored). A match that fails a blocking check is excluded from the analytical layer, and the exclusion is reported.

**As implemented (2026-09-27).**
- Blocking checks: raw checksum, adapter validation (includes unknown provider types), both teams present, at least 1,000 events, contiguous sequence, score reconciliation, and substitutes in the lineup.
- Warnings, which keep the match:
  - clock regressions within a period;
  - coordinates off the pitch;
  - missing metadata;
  - event players missing from the lineup;
  - overlapping position spells;
  - a lineup spell running past a Substitution event.
- Clock regressions are warnings because replay orders by sequence, and 100 of 270 development matches contain one (see [research note 04](../research/04-provider-clock-and-lineup-anomalies.md)).

## Splits (frozen at step 2)
- **Rule:** within each competition-season, sort matches by date, kickoff time, and match ID. The earliest ~70% are **development**, the next ~15% **validation**, and the final ~15% **test**. Cuts fall between dates, so no date straddles two buckets.
  - **Development:** explore freely, invent metrics, tune thresholds.
  - **Validation:** compare detector variants and thresholds.
  - **Test:** untouched until we want a final estimate.
- **Tournaments** follow the same rule. Caveat: knockout matches end up concentrated in test, so tournament test results partly measure knockout football.
- **Already inspected matches** go to development regardless of the rule. Today those are match 3773497 and the three probe 01 matches (265958, 3869420, 3869321).
- **Version-one boundary details (2026-09-27):** choose the pair of whole-date boundaries minimizing the summed absolute distance from cumulative 70% and 85% targets; ties choose the earlier boundaries. Require nonempty buckets. Promote the entire competition-season date group of an inspected match to development, preserving the no-date-straddling rule. Version one has four inspected exceptions and nine additional same-date promotions.
- **Human-review set:** 24 matches drawn from **validation** with a fixed seed, 6 per core league. It is for qualitative judgment and eventual labels (owned by Kassahun), never the whole quantitative test.
- **Version-one review selection:** rank validation identifiers within each core competition-season by SHA-256 of `seed:provider:competition:season:match`, with seed `20260927`, then select the first six. The rule and seed are recorded in the split file. This is deterministic sampling, not fan-usefulness labeling.
- **Storage:** `splits/v1.json` (committed, identifiers only) records the rule, the seed, the generation time, the catalog's source commit, and every match's bucket. A changed split is a new version file, never an edit. Ingestion routes each match to the development or held-out warehouse by its bucket, and both warehouses carry a `splits` table.

## Code layout (when implemented)
| Location | Responsibility |
|---|---|
| `src/regista/adapters/statsbomb/` | Adds `catalog.py` (competitions and match index), `lineups.py`, and `download.py` (URLs pinned to a commit) |
| `src/regista/pipeline/` | Provider-neutral orchestration: manifest, ingest runs, data-quality checks, splits |
| `src/regista/warehouse/` | DuckDB schema (SQL files), writers, analytical builds. The only package allowed to import `duckdb`. |
| `src/regista/domain/` | Adds `matches.py`, `lineups.py`, and `normalized.py` (row records and field availability tags); `ActionType` grows additively |
| `catalog/corpus.toml`, `splits/v1.json` | Committed. Identifiers and choices only, no provider data. |
| CLI | `regista data catalog`, `split`, `download`, `ingest` (normalize, quality, and analytical build in one atomic rebuild), `quality`, `fingerprint` |

## Decisions (Kassahun, 2026-09-27)
- The corpus has roles (core breadth, modern robustness, 360 subset), not one canonical dataset.
- Three buckets (development, validation, test), split chronologically, plus a separate human-review set.
- Splits are frozen right after the catalog, before any download.
- The human-review set comes from validation.
- The first wave is Premier League 2015/16.
- Ligue 1 2015/16 belongs to core breadth, with its three missing matches flagged.
- No machine learning in Phase 2.
- A fan-value probe on three matches originally preceded any bulk download (step 3). **Superseded sequencing decision, 2026-09-27:** the owner requested proceeding with data acquisition now. The first development wave may proceed while viewing judgments remain pending; those judgments still govern fan-value claims and detector promotion.
- Development and held-out matches live in separate warehouse files; research tools only open the development one.
- Normalized fields carry an availability tag, and detectors never read `hindsight` fields.
- Detectors distinguish "no change" from "insufficient data".
- "Unusual for this team" comes from window distributions in earlier matches, never from whole-match averages.

## Open questions
- Which matches testers can legally rewatch for the probe and later human evaluation (Kassahun's choice).
- How labeling works without circularity (labeling what the detector already sees). This is settled with the labeling guide.
- Whether any modern robustness set earns a role beyond checking that results still hold.
