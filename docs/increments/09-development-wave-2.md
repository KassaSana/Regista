# Increment 9: Development ingestion wave 2

Last updated: 2026-09-27

## Decision
The owner asked to grow the development corpus from 270 matches to roughly 800–1,500, preferring diversity over match count, with no new provider. This supersedes the roadmap's "waves 2 and 3 wait until a specific question needs them" for this wave; the owner's request is the recorded reason. No detector tuning or exploratory conclusions are part of it.

Frozen splits are unchanged. Only development matches from `splits/v1.json` were acquired. No validation or test match file was downloaded or opened, and the catalog (`catalog/corpus.toml`) was not changed, so its configuration checksum still matches split version one.

## What the 270-match corpus overrepresented
- **One league:** 266 of 270 matches were Premier League.
- **One season:** 2015/16, and because the split is chronological, only 8 August to 27 February of it.
- **Club football only:** no national teams, and no tournaments apart from 2 inspected World Cup matches.
- **One era:** 2015/16, apart from 3 inspected matches.
- **Few teams:** 27 in total.

## Options considered
The pinned provider index has 80 competition-seasons, and the catalog holds 13 of them, with 1,340 development matches.

| Option | Adds | Total | Why not (or why) |
|---|---:|---:|---|
| All remaining 2015/16 core leagues (La Liga, Serie A, Ligue 1) | ~805 | ~1,075 | More of the same era and format |
| All nine modern-robustness sets only | 262 | 532 | Below the target size |
| **Nine modern-robustness sets + Serie A 2015/16** (chosen) | **530** | **800** | Smallest wave reaching the target. It adds a recent era, national teams from five confederations, tournament group stages, and a second complete league season for baselines. |
| Uncataloged competitions (women's leagues and tournaments, World Cup 2018, Indian Super League) | varies | — | Needs a catalog change and a new split version: an owner decision about corpus roles. Listed as wave-3 candidates. |

Serie A was chosen over La Liga and Ligue 1 2015/16 because:
- La Liga is already present, through Barcelona 2020/21 and one inspected match.
- Ligue 1 2015/16 has 3 missing matches, which weakens team baselines.
- Serie A carries the one cataloged metadata gap, so the quality warning gets exercised on real data.

## Commands

```console
# per competition-season (C:S): 12:27 9:281 7:108 7:235 11:90 43:106 55:43 55:282 223:282 1267:107
uv run regista data download --competition C --season S --report out/downloads/wave-2-C-S.json
uv run regista data download --include-inspected --competition-season 2:27 --competition-season 12:27 \
  ... (all 11 competition-seasons) --verify-only
uv run regista data ingest --include-inspected --competition-season 2:27 --competition-season 12:27 \
  --competition-season 9:281 --competition-season 7:108 --competition-season 7:235 \
  --competition-season 11:90 --competition-season 43:106 --competition-season 55:43 \
  --competition-season 55:282 --competition-season 223:282 --competition-season 1267:107
```

The repeatable `--competition-season C:S` option is new in this increment, because one warehouse build now spans several competition-seasons. A unit test covers it.

## Acquisition
1,060 new files were downloaded: events and lineups for 530 matches. A verify-only pass over the full selection then checked 1,614 files (2,443,923,640 bytes) and downloaded nothing. The manifest holds receipts for 800 matches (1,600 match files), and 0 of them are held out under the current split. `data/raw` is 2.3 GB.

## Verification evidence

| Measure | Value |
|---|---|
| Matches | 800 (270 → 800) |
| Events | 2,829,176 |
| Shots | 20,362 (provider xG total 2,009.8) |
| Passes | 795,266 |
| Carries | 612,119 |
| Goals (excluding shootouts) | 2,097 |
| Teams | 174 (from 27); players 4,435 |
| Date range | 8 Aug 2015 – 2 Jul 2024 |
| Club / international matches | 624 / 176 |
| Validation failures | 0 blocking in 800 of 800 matches; 0 exclusions |
| Warehouse size | 1.5 GB (`data/warehouse/regista.duckdb`) |
| Build time | about 3 minutes |
| Deterministic rebuild | An independent rebuild into a scratch file matched in all 32 tables ("Identical.") |
| Tests | 221 passed (206 synthetic and unit, 15 contract on the expanded warehouse); Ruff and strict Pyright clean |

### Matches by competition and season

| Competition-season | Coverage | Matches | Dates | Events |
|---|---|---:|---|---:|
| Premier League 2015/16 | complete season | 266 | 2015-08-08 – 2016-02-27 | 914,090 |
| Serie A 2015/16 | complete season | 268 | 2015-08-22 – 2016-02-28 | 950,882 |
| La Liga 2015/16 | complete season (1 inspected match) | 1 | 2016-05-08 | 3,359 |
| 1. Bundesliga 2023/24 | single team | 24 | 2023-08-19 – 2024-03-03 | 99,134 |
| La Liga 2020/21 | single team | 25 | 2020-09-27 – 2021-04-10 | 98,487 |
| Ligue 1 2021/22 | single team | 18 | 2021-08-29 – 2022-03-13 | 70,483 |
| Ligue 1 2022/23 | single team | 22 | 2022-08-06 – 2023-03-11 | 87,128 |
| FIFA World Cup 2022 | tournament | 46 | 2022-11-20 – 2022-12-09 | 167,679 |
| UEFA Euro 2020 | tournament | 36 | 2021-06-11 – 2021-06-23 | 129,576 |
| UEFA Euro 2024 | tournament | 36 | 2024-06-14 – 2024-06-26 | 128,732 |
| Copa América 2024 | tournament | 22 | 2024-06-21 – 2024-07-02 | 69,095 |
| Africa Cup of Nations 2023 | tournament | 36 | 2024-01-13 – 2024-01-24 | 110,531 |

Stages: 624 regular season, 174 group stage, 2 quarter-finals (the inspected World Cup matches, the only ones with extra time and a shootout). 207 matches have 360 frames available; none are downloaded (Phase 6).

### Data-quality warnings (no exclusions)

| Warning | Matches |
|---|---:|
| clock_monotonic | 128 (100 Premier League, only 1 Serie A) |
| substitution_ends_lineup_spell | 21 |
| position_spells_consistent | 12 |
| coordinates_on_pitch | 3 |
| provider_metadata_present | 1 (3878540, the cataloged Serie A gap) |

`lineup_consistent` is false for 46 of 1,600 team-matches. The contract tests confirm the research note 04 patterns still hold on the larger corpus:
- Large clock regressions are only first-half Ball Receipts.
- Teams with consistent lineups never have more than 11.02 players on the pitch.

The Ball Receipt timestamp artifact appears to be largely a Premier League 2015/16 phenomenon.

## Coverage cautions for later research
- Single-team seasons describe one team and its opponents, not a league.
- Tournament development matches are group-stage games only; knockouts sit in validation and test.
- Development 2015/16 league data ends in late February, so it has no season run-in.

## Not done (by design)
No detector tuning, no exploratory conclusions, and no catalog or split change.

Wave-3 candidates, each needing a catalog entry and a new split version:
- women's competitions (FA WSL, Women's World Cup 2019 and 2023, Women's Euro 2022 and 2025, NWSL, and others);
- FIFA World Cup 2018;
- Indian Super League 2021/22;
- the remaining La Liga and Ligue 1 2015/16 development matches (already cataloged; no split change needed).
