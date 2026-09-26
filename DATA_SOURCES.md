# Data Sources

Regista's code is public. Provider data is not: it is downloaded locally into `data/` and never committed.

## StatsBomb Open Data

- Source: https://github.com/statsbomb/open-data (terms: `LICENSE.pdf` in that repository).
- Use in Regista: development and research only. No commercial use of the data or of analysis derived from it.
- Attribution: published analysis, screenshots, or write-ups show "Data: StatsBomb" and the StatsBomb logo.
- No redistribution: raw event, lineup, match, or 360 files are never committed, uploaded, or bundled into a public viewer.

> **License terms confirmed by Kassahun: ☐** *(placeholder: the summary above comes from research notes, not a reading of the license. Tick after reading `LICENSE.pdf`.)*

## What is public and what is not

| Public in this repository | Never committed |
|---|---|
| Source code and detectors | Raw provider files (`data/`) |
| Tests with synthetic, hand-built events | Databases built from provider data (`*.duckdb`) |
| Derived visuals and write-ups, with attribution | Copies or excerpts of raw event files |
| Documentation | |

## If Regista ever becomes commercial

Replace StatsBomb Open Data with a provider whose written agreement permits the intended commercial use, before any paid feature exists.

## Not used

- Transfermarkt and FBref: never scraped.
- Player photos, club crests, league logos.
