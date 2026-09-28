# Research note: Chance quality against the scoreline (product direction and sizing)

Last updated: 2026-09-28

## Question

The owner's product direction (2026-09-28, below) asks for insights a fan would not get from the broadcast or the scoreboard. Raw volume ("4 shots in 10 minutes") is too obvious. How often does the development corpus contain the kind of disagreement the owner describes, between the scoreline and the quality of chances created? And what would detecting it require? This note records direction and sizing only. **No detector or Phase 2 experiment changes.**

## Owner product direction (Kassahun, 2026-09-28, in chat)

Recorded as product evidence, not as an instruction to implement:
- Prefer insights that reveal something the viewer may not realize from watching or from the scoreboard.
- Raw volume changes may be too obvious unless context makes them unusual.
- The strongest interest is disagreement between visible outcomes and underlying performance:
  - a team leads 2–1 after scoring unusually difficult or low-quality chances;
  - the losing team has created much better chances but been stopped by the goalkeeper;
  - many low-quality shots against fewer dangerous ones;
  - finishing or goalkeeping unusually strong compared with what similar chances normally produce;
  - a spell that is unusual against historical matches, not merely against the previous 20 minutes.
- Live, the product is a sparse light bulb: opening it should usually reveal something not understood from the broadcast or scoreboard alone.
- Wording must stay factual: "the scoreline doesn't reflect the difference in chance quality so far", never "should be winning".

## Definitions (sizing only)

- **Chance quality:** the sum of the provider's xG (`analytical.team_time_bins.provider_xg`, penalties included) up to a checkpoint.
- **Disagreement:** one team's xG exceeds the other's by at least 1.0 (0.75 as a sensitivity check) while that team is not ahead on goals.
- **Checkpoints:** halftime (all of period 1); 60 minutes (period 1 plus the first 15 minutes of period 2); 90 (periods 1–2). This is a retrospective count over whole periods; no detector reads it.

## Data

- All 800 development matches in the development warehouse. No validation or test data was opened.
- Code: repository commit `c8133f6` plus uncommitted increment 19 work; the inline SQL below.

## Method

```sql
WITH cp AS (
  SELECT 'halftime' AS cpoint, match_id, team_id, sum(provider_xg) AS xg, sum(goals) AS g
  FROM analytical.team_time_bins WHERE period = 1 GROUP BY ALL
  UNION ALL
  SELECT '60 minutes', match_id, team_id, sum(provider_xg), sum(goals)
  FROM analytical.team_time_bins
  WHERE period = 1 OR (period = 2 AND bin_end_seconds <= 900) GROUP BY ALL
  UNION ALL
  SELECT '90', match_id, team_id, sum(provider_xg), sum(goals)
  FROM analytical.team_time_bins WHERE period IN (1, 2) GROUP BY ALL
), pairs AS (
  SELECT a.cpoint, a.match_id, a.xg - b.xg AS xgd, a.g - b.g AS gd
  FROM cp a JOIN cp b ON a.cpoint = b.cpoint AND a.match_id = b.match_id AND a.team_id <> b.team_id
)
SELECT cpoint, count(*) FILTER (WHERE xgd >= 1.0 AND gd <= 0),
       count(*) FILTER (WHERE xgd >= 1.0 AND gd < 0),
       count(*) FILTER (WHERE xgd >= 0.75 AND gd <= 0)
FROM pairs GROUP BY 1;
```

Run it through `regista.warehouse.research.connect_research` on `data/warehouse/regista.duckdb`.

Point-in-time: the shot and its outcome are `known_at_event`; provider xG is `delayed` (probe 01). A live detector could use both, with the xG lag stated.

## Results

| Checkpoint | Matches where a team leads xG by ≥ 1.0 but is not ahead | …and is behind | Same with xG lead ≥ 0.75, not ahead |
|---|---:|---:|---:|
| Halftime | 15 of 800 | 2 | 57 |
| 60 minutes | 38 of 800 | 5 | 73 |
| 90 | 76 of 800 | 25 | 127 |

At a 1.0 margin the disagreement is rare: about 1 in 50 matches at halftime and 1 in 10 at full time. That rarity suits a sparse light bulb.

**What the StatsBomb open event data already carries per shot:**
- provider xG;
- shot type (open play, free kick, corner, penalty) and body part (right foot 10,681, left foot 6,484, head 3,144, other 53);
- technique and first-time flags;
- the key pass (assist) link;
- outcome (goal 2,023, saved 4,615, blocked 5,463, off target 6,753, post 354, and others);
- end location, with height for some shots;
- a freeze frame of player positions at the shot.

Post-shot xG is not provided, so "the goalkeeper carried them" would need a model Regista builds.

**Candidate insights, by how much new machinery each needs:**

| Candidate | Needs | Fits |
|---|---|---|
| Scoreline against chance quality | Provider xG, cumulative | A Phase 2 detector (the roadmap's "Is the pressure dangerous or just possession?"); no model of Regista's own |
| Chance quality against volume (few good chances against many poor ones) | Provider xG per shot | Phase 2 |
| Unusual against historical matches | Distributions from earlier kickoffs only (`team_window_distributions`) | Phase 2 data model, not yet built |
| Finishing over- or under-performance | xG against goals, plus history for "unusual" | Phase 2 descriptive version; history later |
| Goalkeeper performance | A post-shot model (placement and height of on-target shots) | Phase 4, frozen |

## Counterexamples and alternative interpretations

- xG is a provider model, not truth. A 1.0 gap can come from one penalty (0.76 in this data) plus noise. A card would need to exclude penalties or name them, and say whose model it uses.
- A team that leads often sits back, and shots it concedes late may be low quality in number but not in danger. Game state explains some disagreement without any "misleading" scoreline.
- Whole-period sums use hindsight about when the checkpoint falls. A live version must accumulate event by event, and it inherits the xG lag.
- Broadcasters increasingly show xG on screen. Obviousness is lower than for shot counts but not zero.

Confidence: **0.95** in the counts, which are a direct query over the development warehouse. **0.8** that a scoreline-against-chance-quality observation is rare enough to be a sparse card. **0.6** that it would pass the owner's "not obvious from the broadcast" test, which only the owner can judge. These are analytical confidence scores, not calibrated probabilities.

## Owner judgment

<!-- Pending. -->

## Decision

**Record as product direction; implement nothing yet.** Once the Phase 2 gate is decided, the strongest next candidate is a development-only research note on a scoreline-against-chance-quality detector. It stays within Phase 2 (provider xG, no model of Regista's own), and the scope freeze would not need lifting. Goalkeeper and post-shot modelling remain Phase 4.

Data: StatsBomb
