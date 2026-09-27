# Research note: Does more territory come with more threat in the same spell?

Last updated: 2026-09-27

**Status: retrospective analysis complete; no detector change; owner judgment not requested for this note.**
Private working analysis. Data: StatsBomb.

## Question
When a team's territorial activity increases, does the same spell also contain more attacking threat?

A fan asks this as "is the pressure dangerous, or just possession?" (ROADMAP.md, Phase 2 item 8). If territory and threat move together tightly, a territory card adds little to a shots card. If they often diverge, "territory up without more threat" could be worth showing. This note only describes the data. It does not show that any such card helps a fan.

## Definitions
All definitions below are **provisional research definitions for this note**. None is a locked detector definition, except the two taken from AGENTS.md.

**Analysis type.** This is retrospective analysis.
- It pools whole matches.
- It excludes each half's incomplete tail, which needs to know when the period ended.
- It cuts value bins at quantiles computed over the full development corpus.

None of this is replay-eligible. The measurements inside a window use only events inside that window. Each comparison is with the window before it. That shape could be computed point-in-time at the window's end. The table below gives field availability, using the Phase 2 specification's terms.

| Field | Availability | Used for |
|---|---|---|
| Pass start and end location, pass type, pass outcome | `known_at_event` | Final-third entries, field tilt |
| Carries | `delayed` (derived from the next event) | Final-third entries |
| Shot, shot type | `known_at_event` | Shots |
| Provider xG | `delayed` (provider processing) | xG |
| Goal (shot outcome) | `known_at_event` | Only to select the goal-free subset |
| Period end time (`analytical.periods.end_seconds`) | `hindsight` until the whistle | Only to mark the incomplete tail windows |

No `play_pattern`, possession grouping, assist flag, or other hindsight field is used.

**Windows.**
- Each regular-time half is cut into non-overlapping windows of length L (primary L = 10 minutes): [0, L), [L, 2L), and so on.
- The clock is `period_seconds`, which restarts at 0 in each period. So the second half's first window is 45:00–55:00 on the broadcast clock.
- Extra time (periods 3–4, 2 matches) and penalty shootouts (period 5) are left out.
- A window is **complete** when the period lasted at least to its end.
  - Every half lasts at least 44.6 minutes (2,674 s), so with L = 10 windows 1–4 are always complete: 0–40 minutes of each half.
  - The 40–50 minute window is complete only in halves that lasted 50 minutes or more.
- **Stoppage time.** Any time after the last complete window falls in an *incomplete* window. That window is described, but it is excluded from every primary comparison, because its length varies (median 7.0 minutes, 10th–90th percentile 0.9–9.2 minutes). It holds 14.2% of all regular-time shots at L = 10, so the late part of each half, including stoppage time, is under-represented.

**Clock anomalies.** `analytical.event_context.clock_out_of_order` flags events stamped earlier than an event before them in the same period ([research note 04](04-provider-clock-and-lineup-anomalies.md)). That flag is false for all 795,266 passes, 612,119 carries, and 20,362 shots used here. The known anomaly affects only Ball Receipt and period-end events, which this note does not count. Events are kept in their provider-stamped window, and none is corrected.

**Territory measures.** Both are measured for the team in a window.
- **Final-third entries** follow the locked definition (AGENTS.md): open-play completed passes or carries starting at x < 80 and ending at x ≥ 80. Source: `analytical.final_third_entries`.
- **Field tilt**, following the AGENTS.md metric:
  - numerator: the team's completed open-play passes starting at x ≥ 80 in its own attacking frame;
  - denominator: the same count for both teams in the window;
  - share = numerator / denominator.
  - The share is **missing** (not 0.5, not 0) when the denominator is 0.
  - **No minimum denominator has been settled** (increment 8 lists it as an owner decision). This note therefore reports each field-tilt result at minimums of 1, 5, 10, and 20 combined passes, and gives the denominator distribution. None of these minimums is a recommendation.

**Threat measures.**
- **Shots:** all of the team's regular-time shots in the window, including penalties and free kicks. Open-play and non-penalty variants are computed in the output, and penalties are discussed below.
- **xG:** the sum of **StatsBomb's provider xG** (`provider_xg`) over those shots. It is the provider's model, not a Regista model, and it is `delayed` in a live setting.

**Missing values.**
- A window with no shots has a true xG of zero.
- A window with any shot lacking a provider xG value would have *missing* xG, and would drop out of the xG comparisons rather than count as zero. In this corpus 0 of 20,362 shots lack xG, so no window was affected.
- A zero entry count is a true zero only when the window contains events. Every complete window here contains events from at least one team (0 without any event), so no window was treated as a data gap.
- Note that `analytical.team_time_bins.provider_xg` turns missing xG into 0. That is why this note computes xG from `event_context` instead.

**Units of comparison.**
- *Same-window level:* for each team-match, every complete window's value minus that team-match's own mean. This removes team strength and match-level differences.
- *Change:* consecutive complete windows of the same team in the same half, (k − 1, k). The change is the value in k minus the value in k − 1.
- **Overlap.** Primary windows do not overlap. Consecutive pairs share a window, so they are **not independent**. Both teams of a match share events, and one team's field-tilt share is the other's complement. Every interval is therefore a **match-cluster bootstrap**: 1,000 resamples of whole matches, seed 20260927. For speed, the replicates reuse the full-sample ranks.

## Data
- **Matches:** all 800 development matches in the warehouse, which is 1,600 team-matches and 174 teams. There were no exclusions (0 blocking data-quality failures in increment 9).
- **Split bucket:** development only (`splits/v1.json`, version 1). No validation or test data was opened.
- **Coverage is uneven.** Premier League 2015/16 (266 matches) and Serie A 2015/16 (268) supply 65% of the 10-minute pairs. There are also:
  - four single-team club seasons (La Liga 2020/21, Ligue 1 2021/22 and 2022/23, Bundesliga 2023/24), where one team appears in every match;
  - tournament group stages only (World Cup 2022, Euro 2020 and 2024, Copa América 2024, AFCON 2023);
  - one La Liga 2015/16 match.

  League data ends in late February.
- **Provider source:** `hudl/open-data` commit `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`.
- **Warehouse:** `data/warehouse/regista.duckdb`, ingest run `9a6c9d48abd4fa3f`. It was built from git `449aa78` with an uncommitted working tree (`git_dirty = true`; see [increment 10](../increments/10-remote-storage.md)) on DuckDB 1.5.5. It has not been rebuilt from committed code since.
- **Code:** `scripts/research/territory_threat.py`, SHA-256 `5f896937b5d1b1fddb2e385a68689cd0e5aee4069921dc67c8d13bd0bda47ee1`, committed with this note.

## Method
```console
uv run python scripts/research/territory_threat.py --window-minutes 10   # primary
uv run python scripts/research/territory_threat.py --window-minutes 5    # sensitivity
uv run python scripts/research/territory_threat.py --window-minutes 15   # sensitivity
```
- The script opens the warehouse through `regista.warehouse.research.connect_research`, which is read-only and has no external file access.
- It builds a team × half × window grid from `analytical.team_matches` and `analytical.periods`, including empty windows.
- It counts events from `analytical.event_context` and `analytical.final_third_entries` (the `WINDOWS_SQL` query in the script).
- Everything else is plain Python: average-rank Spearman coefficients, the cluster bootstrap, and value bins.
- Value bins cut at the 20/40/60/80% values of the change. Ties stay in one bin, so bins are unequal in size.
- Full results are written to git-ignored `out/research/05-territory-threat/results-<L>-minutes.json`.

## Results
**Sample (10-minute windows):**
- 16,664 team-windows, of which 13,464 are complete and 3,200 incomplete.
- 10,264 consecutive pairs from 800 matches. 5,926 of those pairs have no goal by either team in either window.

**Distributions per complete team-window:**

| Measure | Mean | 10% | 25% | Median | 75% | 90% |
|---|---:|---:|---:|---:|---:|---:|
| Final-third entries | 4.76 | 1 | 3 | 4 | 6 | 9 |
| Shots | 1.30 | 0 | 0 | 1 | 2 | 3 |
| Provider xG | 0.129 | 0 | 0 | 0.048 | 0.155 | 0.368 |
| Field-tilt denominator (both teams) | 15.0 | 6 | 9 | 14 | 19 | 26 |

- 31.3% of complete windows contain no shot.
- Field tilt is undefined (denominator 0) in 0.2% of windows.
- The denominator is below 5 in 5.2% of windows, below 10 in 26.1%, and below 20 in 75.9%.

**1. Same window, relative to the team's own match average.**
- Entries vs shots: Spearman ρ = **0.23**, 95% CI 0.22–0.25.
- Entries vs xG: ρ = **0.13**, 95% CI 0.11–0.15.
- In windows above the team-match's mean entries, the team averages +0.25 shots and +0.017 xG relative to its own match mean. In windows below it, the team averages −0.21 shots and −0.014 xG.

**2. Change from the previous window.**
- Entries change vs shots change: ρ = **0.21** (0.19–0.23).
- Entries change vs xG change: ρ = **0.13** (0.11–0.16).
- In goal-free pairs, which avoids score changes altering behaviour, the figures are ρ = 0.21 (0.18–0.23) and 0.16 (0.13–0.19).

| Entries change (k − 1 → k) | Pairs | Mean change in shots | Mean change in xG | Shots up / down | No shot in k | Shots in k | xG per entry in k |
|---|---:|---:|---:|---|---:|---:|---:|
| −16 to −3 | 2,119 | −0.38 | −0.019 | 28% / 47% | 36% | 1.22 | 0.042 |
| −2 to −1 | 2,290 | −0.22 | −0.020 | 30% / 40% | 37% | 1.12 | 0.035 |
| 0 to +1 | 2,601 | +0.10 | +0.012 | 37% / 31% | 31% | 1.25 | 0.029 |
| +2 to +3 | 1,812 | +0.39 | +0.036 | 45% / 28% | 23% | 1.52 | 0.025 |
| +4 to +16 | 1,442 | +0.60 | +0.045 | 52% / 24% | 19% | 1.72 | 0.018 |

*xG per entry in k* is the bin's total xG in window k divided by its total entries in k. It is a pooled ratio: shots that do not follow an entry (set pieces, high regains) are also in the numerator.

Effect size in plain terms: the largest entry increases (+5.6 entries on average) come with about **+0.6 shots and +0.045 provider xG** in the same 10 minutes. Shots rise in 52% of those pairs. **Threat per entry falls steadily as the entry increase grows**, from 0.042 to 0.018 xG per entry.

**3. Field-tilt change vs threat change.** Pairs are kept when both windows meet the minimum denominator.

| Minimum denominator | Pairs (share of all) | Matches | ρ with shots change | ρ with xG change |
|---:|---:|---:|---|---|
| 1 | 10,222 (99.6%) | 800 | 0.28 (0.25–0.30) | 0.21 (0.19–0.24) |
| 5 | 9,254 (90.2%) | 800 | 0.28 (0.26–0.30) | 0.22 (0.19–0.24) |
| 10 | 5,858 (57.1%) | 756 | 0.28 (0.25–0.31) | 0.21 (0.18–0.24) |
| 20 | 974 (9.5%) | 252 | 0.28 (0.21–0.34) | 0.18 (0.11–0.25) |

- At a minimum of 5, the top fifth of tilt increases (+0.28 to +1.00 share) average +0.73 shots and +0.070 xG.
- Unlike entries, xG per entry stays roughly flat across tilt bins (0.025–0.030).
- The association hardly depends on the minimum. What changes is which pairs survive: a minimum of 20 keeps fewer than one pair in ten, drawn mostly from high-volume matches.

**4. Heterogeneity** (entries change vs shots / xG change, ρ with 95% CI):

| Competition-season | Pairs | Matches | Shots | xG |
|---|---:|---:|---|---|
| Premier League 2015/16 | 3,360 | 266 | 0.20 (0.16–0.24) | 0.14 (0.10–0.18) |
| Serie A 2015/16 | 3,328 | 268 | 0.21 (0.17–0.25) | 0.12 (0.08–0.15) |
| FIFA World Cup 2022 | 672 | 46 | 0.24 (0.15–0.32) | 0.12 (0.03–0.21) |
| Africa Cup of Nations 2023 | 518 | 36 | 0.29 (0.20–0.38) | 0.26 (0.16–0.35) |
| UEFA Euro 2024 | 476 | 36 | 0.27 (0.17–0.37) | 0.15 (0.04–0.25) |
| UEFA Euro 2020 | 460 | 36 | 0.18 (0.11–0.26) | 0.15 (0.08–0.24) |
| La Liga 2020/21 (single team) | 318 | 25 | 0.27 (0.14–0.39) | 0.18 (0.07–0.29) |
| 1. Bundesliga 2023/24 (single team) | 310 | 24 | 0.15 (0.04–0.25) | −0.00 (−0.11–0.11) |
| Copa América 2024 | 300 | 22 | 0.19 (0.04–0.34) | 0.13 (−0.04–0.29) |
| Ligue 1 2022/23 (single team) | 280 | 22 | 0.11 (−0.05–0.25) | 0.05 (−0.11–0.20) |
| Ligue 1 2021/22 (single team) | 230 | 18 | 0.21 (0.07–0.34) | 0.20 (0.07–0.32) |

- The shots association is positive in every group. Its interval excludes zero in all but Ligue 1 2022/23.
- The xG association is near zero in Bundesliga 2023/24, and its interval includes zero in three small groups.
- **Repeated teams.** Computing one coefficient per team (teams with at least 30 pairs; 77 teams) gives a median ρ of 0.21 for shots, positive for 94% of teams, and a median of 0.12 for xG, positive for 84%. No small set of heavily repeated teams drives the result.
- By half: first halves give ρ 0.18 for shots and 0.12 for xG; second halves give 0.23 and 0.15.

**5. Sensitivity to window length** (the same definitions, L = 5 and 15 minutes):

| L | Complete windows | Pairs | Shots in incomplete windows | Level ρ, shots / xG | Change ρ, shots / xG | Tilt change (min 5) ρ, shots / xG |
|---:|---:|---:|---:|---|---|---|
| 5 | 29,478 | 26,278 | 5.5% | 0.23 / 0.15 | 0.21 / 0.16 | 0.28 / 0.23 |
| 10 | 13,464 | 10,264 | 14.2% | 0.23 / 0.13 | 0.21 / 0.13 | 0.28 / 0.22 |
| 15 | 9,574 | 6,374 | 8.0% | 0.25 / 0.12 | 0.21 / 0.11 | 0.29 / 0.21 |

- The falling xG per entry holds at every length: 0.045 → 0.015 at L = 5, and 0.038 → 0.020 at L = 15.
- At 5 minutes, 55% of windows have no shot and 71% have a tilt denominator below 10. Sparsity rises sharply as windows shrink.

## Counterexamples and alternative interpretations
**Counterexamples** (10-minute windows).
- Of the 1,442 pairs with the largest entry increases (+4 or more, the top ~14%):
  - **271 (19%) have no shot at all** in the later window;
  - 339 (24%) have fewer shots than the window before.
- Of the 1,393 pairs where entries fell by 4 or more, 389 (28%) have *more* shots.
- The largest entry spells without a shot are listed below. The three probe matches are excluded from examples, because the owner has not viewed them yet.

| Match | Team | Half, minutes | Entries | Tilt passes (own / both) | Shots | xG |
|---|---|---|---|---|---|---|
| 3802802 | Paris Saint-Germain (Ligue 1 2021/22) | 2nd, 30–40 | 4 → 20 | 14/27 → 29/33 | 5 → 0 | 0.52 → 0 |
| 3879550 | Fiorentina (Serie A 2015/16) | 2nd, 10–20 | 12 → 18 | 24/24 → 28/35 | 2 → 0 | 0.07 → 0 |
| 3753997 | West Ham United (Premier League 2015/16) | 2nd, 20–30 | 7 → 16 | 7/10 → 13/14 | 4 → 0 | 0.53 → 0 |
| 3788750 | Spain (Euro 2020) | 2nd, 10–20 | 9 → 16 | 13/16 → 38/40 | 1 → 0 | 0.15 → 0 |
| 3788751 | Germany (Euro 2020) | 2nd, 30–40 | 9 → 16 | 19/20 → 17/20 | 1 → 0 | 0.05 → 0 |
| 3754292 | Newcastle United (Premier League 2015/16) | 1st, 10–20 | 6 → 15 | 13/14 → 11/14 | 4 → 0 | 0.26 → 0 |

These are exactly the "territory up without more threat" spells the probe's territory prototype was designed to surface. They are common enough that they do not fit a simple "more territory means more danger" rule.

**Alternative interpretations.**
- **Shared cause, not a link between the two.** A team with more of the ball does more of everything. Both measures may just track possession, or an opponent that has dropped deep.
- **Partly by definition.** Most shots are taken from the final third, and tilt passes start there. Some positive association is built in and would appear even with no tactical meaning. This is also why field tilt, measured in the same zone as most shots, correlates more strongly than entries.
- **Regression to the mean.** Grouping by *change* over-selects pairs whose earlier window was unusually low or high. The same-window analysis (item 1), which uses no change, gives a similar ρ. That limits, but does not rule out, this explanation.
- **Falling threat per entry** may be:
  - a genuine "sterile pressure" pattern, where opponents defend deep and shots come from worse positions;
  - an artefact of dividing by a larger count, since xG is capped by the number of shots a spell can hold;
  - shots that follow no entry (set pieces, high regains), which inflate the ratio in windows with few entries.

  This note does not separate these explanations.
- **Game state.** A trailing team gains territory against a deep block. Excluding pairs with a goal leaves the result about the same (ρ 0.21 and 0.16), but the score state before the pair was not controlled.
- **Penalties** (218 shots, 170.8 xG, 8.6% of regular-time xG) add large, lumpy xG unrelated to territory. The non-penalty variant was computed, but it is not reported separately here.
- **Coverage.** Two 2015/16 leagues supply most pairs, and single-team seasons follow one dominant team. The results describe this corpus, not football in general.

## Limitations
- The analysis is retrospective. The windows are fixed clock slices, not the rolling "last 10 minutes at each event" a detector would use, and quantile bin cuts use the whole corpus.
- The last minutes of each half, including stoppage time, are excluded from comparisons (14% of shots at L = 10).
- Only the change against the immediately preceding window is studied. "Compared with earlier in this match" and "compared with this team's normal" are not.
- The warehouse was built from a dirty tree (run `9a6c9d48abd4fa3f`). The results should be re-checked once it is rebuilt from committed code, where identical fingerprints are expected.
- Nothing here measures fan usefulness, timeliness, or whether a card would be understood.

## Confidence
Confidence scores are my judgment of how well the evidence supports each statement. They are not calibrated probabilities.
- **0.85 (high)** that, in this development corpus, spells with more territory than the same team's neighbouring or average spells also contain modestly more shots and provider xG. It is consistent across three window lengths, both halves, every competition group for shots, 94% of repeated teams, the goal-free subset, and every field-tilt minimum. The effect is small (ρ about 0.1–0.3).
- **0.6 (medium)** that threat per entry genuinely falls when entries rise sharply. The pattern holds at every window length, but a ratio artefact and regression to the mean are plausible and untested.
- **0.3 (low)** that any of this generalises beyond 2015/16 Europe's top two leagues and 2020s tournament group stages. The minority groups are small and one (Bundesliga 2023/24) differs.
- **None (not assessed)** on whether a fan would find a "territory without threat" or "territory with threat" card useful.

## Owner judgment
Kassahun's judgment of fan usefulness. Agents leave this section empty.

| Match, time | Observation | Correct? | Timely? | Added understanding? | Attention cost | Repetitive? | Keep or drop | Better at halftime or after? | Notes |
|---|---|---|---|---|---|---|---|---|---|

## Decision
**Investigate further; no detector change.** This note does not tune or promote any detector or prototype.
- **What the evidence supports:** territory and threat move together only loosely within a match. A territory increase is a weak signal of more shots and xG, and spells with a large territory increase and no shot are common (about one in five). Territory and threat should therefore stay separate measures, shown side by side, as the probe's territory prototype already does. Neither should be read as a proxy for the other.
- **What it does not support:**
  - any causal claim;
  - a claim that a territory card is useful, or that "sterile pressure" is a real tactical pattern rather than an artefact;
  - any field-tilt minimum (the association does not depend on it, so this analysis cannot choose one);
  - any statement about validation or test data.
- **Smallest next experiment:** repeat the change analysis with "earlier in this match" as the comparison (the probe prototype's framing), computed point-in-time at each window end and split by score state before the window. Check whether falling xG per entry survives with shots that did not follow an entry left out. This uses the same script and warehouse, with no new data.
- **Owner feedback needed:** the three-match viewing probe (`docs/research/probe-01.md`). Only it can say whether a "territory up, threat not up" card is worth a fan's attention. Owner decisions on the field-tilt minimum and box-entry definition remain open (increment 8).

## Addendum (2026-09-27): re-checked on a clean build
The canonical warehouse was rebuilt from committed code: run `aa59531475ecb2a5`, git `7251c15`, `git_dirty = false`, 800 of 800 matches. The 10-minute results reproduced identically; every field except provenance matched. The dirty-tree limitation above no longer applies to the 10-minute results.
