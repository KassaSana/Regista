# Research note: Fan-value probe 01

Last updated: 2026-09-28

**Status: sheets generated; full-match viewing declined by Kassahun on 2026-09-28.** The owner judgment columns remain blank. This proposed usability test does not establish fan value; automated development-only evaluation continues in [research note 12](12-side-shift-automated-audit.md).

An [agent mechanical pre-review](03-probe-01-mechanical-review.md) reproduced the observation counts and checked sampled prefixes on 2026-09-27. It records implementation limitations and clustered observations; it does not supply the owner judgments or complete this probe.

## Question
Do short, evidence-backed observations about how a match is changing help a fan follow it, and when: during play, at halftime, or afterwards? Which kinds of observation are worth building into detectors, and which should be dropped?

## Definitions
Every observation compares the last 10 minutes of the current period with everything earlier in the match (comparison axis: earlier in this match). The prototype thresholds were **fixed in code before the first run** and are initial guesses, not tuned values. Each kind has a 10-minute cooldown per team that resets at a new period. Penalty shootouts are ignored.

| Kind | Claim | Fires when | Could not evaluate when |
|---|---|---|---|
| Attacking side | Changed | The Phase 1 detector, unchanged ([specification](../specs/phase-1-attacking-side-shift.md)) | Not reported by this detector yet |
| Territory (prototype) | Changed, with threat shown beside it | The team's share of both teams' completed open-play passes starting at x ≥ 80 (field tilt, AGENTS.md) is at least 65% in the window and at least 20 points above earlier. The sentence adds the team's shots and xG in the window. | Fewer than 10 such passes in the window, or fewer than 20 earlier |
| Involvement (prototype) | Changed | A player's share of his team's open-play pass attempts is at least 20% in the window and at least 10 points above his share earlier while he was on the pitch. The largest increase wins. | The team made fewer than 25 open-play passes in the window, or no player on the pitch has 40 earlier team passes to compare with |
| Chances (prototype) | Changed (threat) | The team has at least 3 shots in the window, at a rate at least twice its earlier rate. The sentence gives shots and xG for both periods. | Less than 20 minutes of earlier play to compare with |

## Data
| Shape | Match | StatsBomb ID | Official full replay |
|---|---|---|---|
| Dominant | Barcelona v Espanyol, La Liga, 8 May 2016 | 265958 | [FC Barcelona](https://www.fcbarcelona.com/en/videos/816206/barca-5-0-espanyol-201516-full-match) (may need a free account) |
| Balanced | Croatia v Brazil, World Cup quarter-final, 9 December 2022 | 3869420 | [FIFA on YouTube](https://www.youtube.com/watch?v=HxBqMbI5kqQ) |
| Game-state shift | Netherlands v Argentina, World Cup quarter-final, 9 December 2022 | 3869321 | [FIFA on YouTube](https://www.youtube.com/watch?v=QIpZ1pad73w) |

- Split bucket: all three are **development** under the "already inspected" rule (Phase 2 specification), as is match 3773497.
- Provider source: `hudl/open-data` commit `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`, fetched into the local sparse checkout (`data/statsbomb/`). No bulk download.
- Code: `scripts/research/probe_01.py`, on repository commit `449aa78` plus the uncommitted Phase 1 and Phase 2 work.

## Method
```console
uv run python scripts/research/probe_01.py
```

This writes one sheet per match to `out/probe-01/<match>.md` (git-ignored). Each sheet lists the observations in match-clock order, with empty judgment columns and a summary of the minutes in which each prototype could not evaluate a team. The Phase 1 cards come from the real detector through `regista.domain.replay`. The prototypes read the raw event file in provider order and, at each event, use only events at or before it.

**Point-in-time check:**

| Field | Availability | Used by |
|---|---|---|
| Pass start location, pass type, pass outcome, passer | `known_at_event` | Territory, Involvement |
| Shot, shot xG (the provider's model) | `known_at_event` for the shot; the xG value is `delayed` by provider processing in a live feed | Territory, Chances |
| Starting lineups, substitutions, sendings-off | `known_at_event` | Involvement (who is on the pitch) |
| Player nicknames from lineups | Known before kickoff | Display only |
| Carries | `delayed` | Attacking side (Phase 1) |

No `hindsight` field is used.

**Limitations of the method:**
- The prototypes are throwaway research code without tests. Any that survive become real detectors, with the required firing, quiet, and suppression tests.
- Sheet times are StatsBomb's match clock. It follows the broadcast clock, with extra time running on from 90:00.

## Results
Recorded before viewing, and deliberately free of spoilers.

| Match | Attacking side | Territory | Involvement | Chances | Total |
|---|---:|---:|---:|---:|---:|
| Barcelona v Espanyol | 2 | 0 | 6 | 1 | 9 |
| Croatia v Brazil | 4 | 7 | 6 | 3 | 20 |
| Netherlands v Argentina | 1 | 6 | 6 | 3 | 16 |

Mechanical notes (agent), to check against the viewing:
- **Volume.** Up to 20 observations in a 120-minute match is busy against the principle "sparse beats busy". The attention-cost and repetition columns should show whether that matters. The thresholds stay as they are until the judgments are in.
- **Clusters.** The cooldowns are per kind and per team, so different kinds can fire within a minute of each other. They also reset at each new period, which includes extra time.
- **"Chances have picked up"** can fire on 3 low-quality shots. The xG is shown, but the verb may overstate it.
- **Involvement early in a match** compares against only the first few minutes, a thin baseline.
- **Wording.** The Phase 1 template produces "Netherlands's" for team names that end in s.

## Prepared sheets (checked 2026-09-27)
The sheets remain available, but there is no planned full-match viewing. Nothing here is a judgment.
- **Reproducible.** From committed code (`scripts/research/probe_01.py`, SHA-256 `bbe5b7e0…c520`, unchanged), `uv run python scripts/research/probe_01.py --output <empty directory>` regenerated all three sheets byte-for-byte identical to the existing `out/probe-01/` sheets. The sheets are git-ignored local files, because they describe provider events.
- **Original viewing steps, if the owner revisits this method:**
  1. Open one sheet from `out/probe-01/` next to its official replay (links under Data).
  2. Read a row only when the replay clock reaches it.
  3. Fill in every judgment column on the sheet.
  4. Afterwards, answer the three per-match questions under Owner judgment, and ask to have the rows transferred here.
- **Avoid priming.** [Research note 05](05-territory-and-threat.md) studies how territory relates to threat across the development corpus. It never names these three matches, but reading it first could colour your view of the Territory observations. Read it after viewing.

### Windows checkout verification (2026-09-28)

The four inspected development matches were fetched through the pinned
`regista data download --include-inspected` pipeline into `data/raw/`. A
`--verify-only` run checked all 22 source files (18,240,054 bytes) and fetched
nothing. The probe generator now reads that pipeline's location, and regenerated
the three sheets in `out/probe-01/` with the same per-kind counts shown above.
The sheets and provider files remain git-ignored. Owner viewing and judgments
are still pending.

## Counterexamples and alternative interpretations
To be filled in after viewing.

## Owner judgment
Kassahun's judgment of fan usefulness. Agents leave this section empty. Full-match viewing was declined on 2026-09-28, so no judgment is recorded.

For each match, also record:
- whether you already knew how the match went;
- whether you would use Regista for another match;
- which one card, if any, would have made you look away from the television.

## Decision
The full-match viewing method was declined by the owner. The sheets remain available, and automated checks proceed without claiming a fan-usefulness result.
