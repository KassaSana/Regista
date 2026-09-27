# Research note: Probe 01 mechanical review

Last updated: 2026-09-27

**Status: agent mechanical review complete; owner viewing judgments pending.**
Private working analysis. Data: StatsBomb. This note does not approve bulk ingestion or replace the owner-led probe.

## Question

What can be checked about the existing three-match probe before the owner watches, and which limitations must be resolved before its prototypes become production detectors?

## Definitions

Use the unchanged definitions in [probe 01](probe-01.md) and the [Phase 1 specification](../specs/phase-1-attacking-side-shift.md). A cluster flag here means two adjacent observations in the combined timeline, within the same period, separated by at most sixty seconds. It measures proximity, not semantic repetition or distraction.

A prefix check compares prototype output from a truncated event sequence with full-replay output up to the same period/clock boundary. Cuts extend through all events at the selected second to avoid ambiguous equal-clock ordering. These are sampled regression checks, not a proof for every possible stream.

## Data

- Only existing development matches `265958`, `3869420`, and `3869321`; three matches, with no new event acquisition or held-out event reads.
- Provider commit: `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`.
- Code: `449aa7800906fb77ac4b289411c4b803bfecd465` plus the existing uncommitted Phase 1/2 work and new catalog increment. The probe script itself was unchanged; SHA-256 `bbe5b7e0d0f0ba713347b172ee78a0a03adf3a174c8655bc181d4503161cc520`.
- Results below use sheet numbers in the original probe order. No team names, scores, player names, or card timestamps are reproduced.

## Method

```console
uv run --no-sync python out/probe-01-mechanical-review/review.py
```

The local review script and `results.json` remain in ignored `out/probe-01-mechanical-review/`. It replays the three prototype rules with anonymous display names, combines them with production side-shift observations, counts proximity flags, and checks prefixes near 25%, 50%, and 75% of event count for each match. Counts are regenerated using the original implementations; this is not independent arithmetic verification of each prototype card.

Point-in-time review: event order, period/clock, acting team/player, locations, pass type/outcome, lineups, substitutions, and sendings-off are known at the event. Carries and provider xG are delayed. The observed prefix checks use no whole-match aggregates as detector inputs. A finalized file cannot prove live availability or latency.

## Results

| Sheet | Side shift | Territory | Involvement | Chances | Total observations | Adjacent pairs within sixty seconds |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 2 | 0 | 6 | 1 | 9 | 1 |
| 2 | 4 | 7 | 6 | 3 | 20 | 2 |
| 3 | 1 | 6 | 6 | 3 | 16 | 2 |

All 45 observations reproduce the previously recorded counts. All nine sampled prototype prefix checks pass. No adjacent observations share the exact same second. There are five proximity flags; these are candidate viewing-review points, not five proven problems. Overlapping windows and observations from the same match are dependent.

Code review identifies limits on what these checks establish:

- Prototype observations store text and clock but no supporting event identifiers. The production side-shift detector retains evidence internally, but the combined probe sheet strips it. These sheets are usability drafts, not production evidence-bearing card exports.
- Prototype pass classification treats unknown pass types as open play; the production adapter fails loudly. Prototype promotion needs that stricter provider contract.
- The chances prototype defaults missing provider xG to zero. That is an implementation risk, not a claim that these files contain missing xG. A production detector must distinguish missing evidence from zero threat.
- The involvement baseline filters passes to times when the player was on the pitch; its recent denominator uses all team passes in the window. A partially on-pitch recent window would require an explicit symmetric exposure rule. This review does not claim an observed card is affected.
- Cooldowns operate per kind and team, so different kinds can cluster. The code has no combined-stream suppression rule; usefulness and attention cost still need viewing.
- Eligibility summaries retain the last checked status in each minute and omit cooldown checks. They should not be interpreted as exact elapsed-time coverage.

## Counterexamples and alternative interpretations

A clustered pair could describe two useful, distinct observations. A quiet stretch could mean insufficient evidence rather than no change. Prefix consistency can coexist with poor wording, wrong definitions, or data that was unavailable live. Regenerating output with the same code cannot independently establish numerical correctness.

Confidence: **0.99** that the reported counts and nine sampled checks match this run; **0.95** in the identified code limitations; **not assessed** for fan usefulness or a positive probe decision. These are analytical confidence scores, not calibrated probabilities or user ratings.

## Owner judgment

<!-- Pending Kassahun's viewing. Do not fill this section with agent judgments. -->

## Decision

Investigate further through the owner-led probe. Keep production definitions and thresholds unchanged. These results support preparing the metadata foundation, but they do not establish that a large corpus or the companion experience is worth building. Resolve evidence identifiers, provider contracts, and exposure definitions if a prototype earns promotion. The bulk-download gate remains pending.
