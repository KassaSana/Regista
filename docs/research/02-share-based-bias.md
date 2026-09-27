# Research note: Entry volume and side-shift coverage

Last updated: 2026-09-27

**Status: research complete; decision pending Kassahun.** Private working analysis. Data: StatsBomb. The official logo and the owner's release checks are still required before public circulation. No detector, definition, specification, or threshold was changed.

## Question

Why can the attacking-side shift detector overlook a team with fewer entries, and what would broader coverage cost in noise, delay, and meaning?

The strongest finding is a **coverage disparity caused by entry volume**. This is more precise than saying that the share estimator is biased or that possession alone determines coverage. A team's share of open-play pass attempts is not measured possession time.

## Definitions

Entry, completion, open play, and channel follow the [locked definitions](../../AGENTS.md). The [Phase 1 specification](../specs/phase-1-attacking-side-shift.md) supplies the current defaults: at least eight recent entries in ten minutes, twelve earlier entries, a channel increase of at least 25 percentage points, and a ten-minute team cooldown.

| Research quantity | Exact interpretation |
|---|---|
| Entry rate | Completed open-play final-third entries per ten minutes of provider period-clock span, including stoppage and extra time where present. |
| Eligible evaluation fraction | Evaluation moments that pass both count minimums, divided by moments after the period warm-up. Cooldown does not affect eligibility. The research grid contains five-second ticks **plus entry events**, so this is not an exact fraction of elapsed time. |
| Null cards per team-match | Cards for one simulated team over a 96-minute match with a constant underlying channel mix. Only in this synthetic null are all cards false alarms by construction. |
| Shift hit rate | Fraction of simulated team-matches producing any left-channel card within fifteen minutes of a permanent left-share increase. Earlier cards do not disqualify a hit. |
| Null interval hit | The same left-channel/time-interval criterion when no change was planted. This makes chance hits visible. |
| Attempted entry sensitivity | Include incomplete open-play passes whose **recorded** start/end locations cross the boundary, alongside carries. Recorded endpoints need not be intended destinations; this is not a pure pass-completion measure. |

## Data

- Four already inspected development matches: `3773497`, `265958`, `3869420`, and `3869321`; eight team performances and 485 completed entries. No new matches, validation data, or test data were opened.
- Development membership follows the already-inspected exception in the [Phase 2 specification](../specs/phase-2-data-model.md). A frozen split file does not yet exist; this study neither creates nor substitutes for it.
- Probe matches retain opaque labels A/B/C and teams 1/2. Their mapping stays private. Match identifiers above are not listed in label order. No probe scores, named teams, or card times appear here.
- Provider: local sparse checkout of `hudl/open-data`, commit `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`, rechecked on 2026-09-27. Shootouts are excluded from the real-data summaries; periods one through four are retained.
- Code: `449aa7800906fb77ac4b289411c4b803bfecd465` plus the existing uncommitted Phase 1/2 work. Original run fingerprints: working-tree difference `03ad733a1aee8efc`, untracked source `529bc10a006c12f7`, detector `d66ede08ea417b9d`. The detector SHA-256 was rechecked: `d66ede08ea417b9dcb799497163256ee7984f9357ec84cabb86f0c91f32e7d5c`.
- Synthetic study: 210 parameter cells, 400 null and 400 shifted team-matches per cell, with common seeded streams across rules. These are 168,000 replay executions, not 168,000 independent real matches. The earlier 60-replicate quick run is superseded.

## Method

The approved scope keeps scripts and the static artifact outside the repository. The recovered bundle is at:

```text
/private/tmp/claude-501/-Users-kassahunsanayew-Main-Projects-Regista/8302595c-08a2-4a57-a84f-7532e421ca9c/scratchpad/share-bias/
```

It contains `core.py`, `simulate.py`, `exposure.py`, `check_real.py`, `check_synthetic.py`, `stickiness.py`, `finish_charts.py`, `sim.json`, `exposure.json`, `NOTES.md`, `verification.json`, and `report.html`. A local archive is supplied alongside the report; preserve it because temporary directories are not durable storage. Raw records and the private label mapping are excluded from that archive.

From the repository root, substitute the bundle path for `<bundle>`:

```console
uv run --no-sync --with numpy --with scipy python <bundle>/check_synthetic.py
uv run --no-sync python <bundle>/check_real.py
uv run --no-sync --with numpy --with scipy python <bundle>/simulate.py
uv run --no-sync python <bundle>/exposure.py
uv run --no-sync --with matplotlib python <bundle>/finish_charts.py
```

The harness uses the repository path recorded in `core.py`; adjust that path if moving the bundle. Package versions and checksums are recorded in `verification.json`. These tools are temporary research dependencies, not project dependencies.

**Simulation.** Entries arrive at rates one through fourteen per ten minutes, independently within one-second clock resolution. Two periods last 47 and 49 minutes. Channels have probabilities `(0.40, 0.20, 0.40)`, rounded from the development sample's pooled mix `(0.398, 0.200, 0.402)`. At the synthetic second-half fifteenth minute, the left share increases by thirty percentage points to 0.70; the other shares shrink proportionately. Separate sensitivity cells use twenty- and forty-point increases. Bursty arrivals multiply each five-minute block's intensity by an independent gamma variable with shape five and mean one. Channels remain independent in that sensitivity.

For speed, the recovered experiment reimplemented the rule instead of feeding every simulated stream through the production detector as originally planned. This deviation was checked: the current rule matches production on all four development matches, including all nine cards' channels, clocks, counts, and teams. A further 120 synthetic streams match on 286 card clocks/channels. The existing repository tests separately cover prefix invariance. These checks support current-rule equivalence; they do not validate every experimental variant as a production implementation.

**Permutation reference.** For each team, keep entry times and total channel counts, shuffle channel labels 1,000 times, and replay. This assumes exchangeable labels and destroys temporal structure. It is a reference distribution, not an estimate of real-world false-positive rate. The saved summaries do not contain an observed-statistic tail test.

**Point-in-time check.** Each replay reads only the prefix: provider order, period, clock, team, pass type/outcome, and movement locations are known at the event; carries are delayed. No possession grouping, assist flags, future events, or other hindsight fields feed a card. Whole-match exposure totals, pooled channel proportions, entropy, and permutations are retrospective research calculations only. They are not runtime detector inputs. Finalized-file checks cannot establish live delivery latency.

## Results

### Simulation: a large coverage/noise tradeoff

| Setting | Entries per ten minutes | Eligible moments | Null cards per team-match | Shift hits | Null interval hits |
|---|---:|---:|---:|---:|---:|
| Current | 3 | 0.6% | 0.073 | 12/400 (3.0%) | 4/400 (1.0%) |
| Current | 10 | 67.3% | 3.435 | 323/400 (80.8%) | 97/400 (24.3%) |
| Minimums reduced to one each, research only | 3 | 90.8% | 7.198 | 289/400 (72.3%) | 187/400 (46.8%) |
| Minimums reduced to one each, research only | 10 | 98.7% | 5.310 | 340/400 (85.0%) | 112/400 (28.0%) |

The settings above illustrate the sweep; they are **not recommended replacement thresholds**. At low volume, removing the count protection produces many more hits but also many chance alerts. The same-interval null hit rate is essential context for the apparent improvement.

An independent analytical check supports the mechanism: for a stationary Poisson arrival process, a ten-minute window has at least eight entries with probability 1.19% at rate three, versus 77.98% at rate ten. The additional baseline gate further limits eligibility. The reported replay fractions also include extra evaluations at entry times.

At 400 replicates, pointwise 95% Wilson intervals for current-rule hit rates are about **1.7–5.2%** at rate three and **76.6–84.3%** at rate ten. The worst-case Monte Carlo margin is about five percentage points. These intervals measure simulation randomness, not football-model uncertainty; they are not simultaneous confidence bands across the sweep. Saved aggregates do not support paired uncertainty estimates between variants or confidence intervals for mean null-card counts.

Bursty arrivals preserve the gap: current-rule hits become 5.5% and 75.3% at rates three and ten. Across twenty- to forty-point shifts, hits range from 2.3% to 5.8% at rate three and 66.8% to 89.3% at rate ten. This supports the mechanism under the tested sensitivities, not under every pattern of football play.

### Development matches: a mechanism check, not a population estimate

| Performance | Entries | Entries per ten minutes | Open-play pass-attempt share | Eligible moments | Actual cards | Mean shuffled-channel cards |
|---|---:|---:|---:|---:|---:|---:|
| C1 | 18 | 1.94 | 31.0% | 0.0% | 0 | 0.000 |
| Real Madrid, 3773497 | 30 | 3.11 | 31.6% | 0.0% | 0 | 0.000 |
| B1 | 50 | 3.58 | 47.6% | 1.9% | 0 | 0.362 |
| B2 | 57 | 4.08 | 52.4% | 20.6% | 1 | 1.877 |
| A2 | 68 | 5.23 | 50.0% | 18.8% | 2 | 1.413 |
| A1 | 81 | 6.23 | 50.0% | 31.6% | 2 | 2.561 |
| C2 | 85 | 9.17 | 69.0% | 48.7% | 2 | 3.011 |
| Barcelona, 3773497 | 96 | 9.95 | 68.4% | 54.8% | 2 | 3.277 |

The recent-count minimum is the **first blocking condition** in 65.5–100% of eligible-age evaluations for the six lower-rate performances. Baseline failures are counted only after the recent gate passes; this is not an isolated causal decomposition of the two gates. Real Madrid reaches eight entries in its largest exact half-open ten-minute window, but never satisfies both gates together. This corrects the earlier rough maximum of nine without changing its zero-card conclusion.

Balanced pass shares do not guarantee coverage: B1/B2 have roughly 48/52 shares, yet low entry rates and highly unequal eligibility. Entry timing also matters. B2's 20.6% eligibility is far above the constant-rate simulation's 3.0% at nearby rate four; A1's 31.6% exceeds 18.9% at rate six. Barcelona's 54.8% is below 67.3% at rate ten. These are approximate rate comparisons, **not successful numerical calibration**. Different durations, temporal clustering, warm-ups, and channel mixes limit the comparison. Extra-time real matches are not normalized to the synthetic 96-minute duration.

Shuffling channels often generates cards. This shows that card counts alone cannot establish tactical signal. It does **not** show that individual real cards are false, statistically equivalent to noise, or unhelpful to fans.

Counting attempts increases Real Madrid's eligibility from 0.0% to 2.1%, and C1's from 0.0% to 2.9%. Their completed-entry/attempt ratios are 65.2% and 54.5%, versus 92.3% for Barcelona. The association is descriptive and partly mechanical because completed-entry volume itself includes completion. These data do not identify a causal effect of direct playing style.

## Hypotheses, counterexamples, and confidence

Scores express analytical confidence in the stated claim, not calibrated probabilities, statistical confidence intervals, or fan-usefulness ratings.

| Hypothesis | Evidence for | Evidence against / unresolved | Confidence after review |
|---|---|---|---:|
| Minimum counts drive low-volume invisibility | Code, analytical count probability, simulated sweep, and real first-block reasons agree. | Match timing also matters; four selected matches cannot quantify league-wide disparity. | 0.98 for mechanism; 0.65 for wider magnitude |
| Relaxing gates exchanges coverage for noise | Low-rate null cards rise from 0.073 to 7.198 when minimums fall to one each. | Null model is stylized; a useful observation need not be a statistical change-point discovery. | 0.97 under this model |
| Low-rate teams have fewer genuine shifts | Possible explanation for some real zero-card matches. | No labeled true shifts. High whole-match channel entropy does not measure temporal stability. | 0.20; unresolved |
| Fixed-count windows equalize power | They collect more evidence than ten-minute windows for slow teams. | They do **not** equalize fifteen-minute hit rates: last-eight gives 29.3% versus 85.3% at rates three/ten. Null-card median window spans are 22.1 versus 7.1 minutes. | 0.95 for staleness; 0.10 for equal timely power |
| Completion filtering further limits coverage | Attempt sensitivity increases eligibility in all eight performances. | Changes what an entry means; carries and unsuccessful pass endpoints complicate interpretation. No evidence here about direct-style causality. | 0.85 within this sample; 0.35 for generalization |

The original pooled lag-one check found similar observed and independence-expected same-channel rates. That does not prove independence: team effects can cancel, pairs can cross periods, and higher-order or changing channel dependence remains untested. Likewise, the original five-minute dispersion calculation used unequal final-bin exposures; its overdispersion figures are only rough diagnostics, not a fitted arrival model.

Overlapping windows are dependent. Eight performances are paired within only four deliberately selected matches. Neither the number of ticks nor the number of permutations increases the number of independent football matches. No ground-truth shift labels were collected, so real precision, missed moments, and usefulness cannot be estimated here.

## Options and their costs

| Option family | Coverage and noise | Timing and meaning | Decision boundary |
|---|---|---|---|
| Lower count minimums | More eligible low-volume moments; much more null activity with a fixed point threshold. | Keeps the recent-time wording but supports it with fewer observations. | Requires development evaluation and recorded threshold decision. |
| Longer time windows | More low-rate coverage; high-rate noise can fall. Low-rate null cards can rise as previously silent teams become eligible. | Older evidence dilutes short shifts and extends period warm-up. A twenty-minute window detected only 54.5% at rate ten versus 80.8% currently. | Revisit timeliness and baseline sufficiency together. |
| Last N entries | Better access to samples at low volume, but no equal timely detection. | Windows get stale and may cross periods in this prototype; its eligibility denominator includes only entry events. | Changes the locked recent-window semantics; cannot be adopted as a silent parameter change. |
| Sample-size-sensitive threshold | Exploratory binomial tails reduce null activity but also miss changes. At tail .001, rate-ten hits fall to 24.5%, with 0.400 null cards per team-match. | Baseline probability is estimated with add-one smoothing. The prototype ignores that uncertainty and repeated testing. | Not a calibrated test or a recommended replacement. Evaluate finite-match behavior and baseline uncertainty first. |
| Attempted entries | More observations, modest coverage gains for the quietest teams here. | Describes attempted progression, not successful entries; recorded failed-pass endpoints need careful interpretation. | Requires an explicit change to the locked definition. |
| Retain sparse coverage and explain it | Preserves current behavior and makes missing coverage visible. | Silence must not imply that nothing happened. A different observation type might cover low-volume teams. | Fan usefulness and acceptable attention cost belong to Kassahun; no new detector built here. |

Field tilt and involvement shares can also hide the amount of evidence underneath. Algebraically, doubling both numerator and denominator preserves a ratio while changing sample size. This is a reason to inspect their denominators, not evidence that their exact coverage curves match this detector. Multiplying all channel counts by a possession adjustment leaves their shares unchanged and creates no new information; using fractional weighted counts to bypass minimums would need separate justification.

## Sources and interpretation

- **Primary implementation evidence:** [detector](../../src/regista/detectors/attacking_side_shift.py), [entry definitions](../../src/regista/domain/entries.py), the pinned provider checkout, and the reproducible scripts/results described above.
- **Source claim:** [StatsBomb, Introducing Possession-Adjusted Player Stats (2014)](https://blogarchive.statsbomb.com/articles/soccer/introducing-possession-adjusted-player-stats/) explains opportunity limitations in defensive event counts. It motivates checking exposure, but does not validate a correction to attacking-channel shares.
- **Source claim:** [Armitage, McPherson, and Rowe (1969), Repeated Significance Tests on Accumulating Data](https://academic.oup.com/jrsssa/article/132/2/235/7104382) shows why repeatedly applying a fixed-level significance test changes the overall false-positive probability. The existing flat share threshold is not a significance test; the source is directly relevant to interpreting the experimental binomial option. Overlapping checks are not independent tests.
- **Inference:** report null cards and interval-hit probabilities over the whole finite replay, instead of treating a per-look threshold as a match-wide guarantee. No paper supplies the numerical football results in this note.

## Owner judgment

<!-- Reserved for Kassahun. No fan-usefulness judgments have been supplied or inferred. -->

## Decision

**Pending Kassahun.** Research supports documenting the entry-volume coverage gap and the noise/timeliness tradeoffs. It does not establish a best replacement, new threshold, or useful card.

The most consequential next evidence is owner-labeled useful and missed moments in the existing development probe, followed by development-only checks with time-varying and dependent channel choices, a common time-weighted eligibility denominator, and a finite-replay error budget. Any later comparison of finalized variants belongs on validation under the frozen split process; test remains untouched. This research increment stops here.
