# Data Sources

Regista's code is public. Provider data is not: it is downloaded locally into `data/` and never committed.

## StatsBomb Open Data

- Source: https://github.com/hudl/open-data (the old `github.com/statsbomb/open-data` address redirects here).
- Terms: *StatsBomb Public Data User Agreement* (`LICENSE.pdf` in that repository, last updated 8 September 2023).

### What the agreement says, and how Regista complies

| Clause | Requirement | Regista's planned use |
|---|---|---|
| Preamble, 1.1 | The data is for analysis, research, and shared understanding; analysis and conclusions may be shared publicly. | Learning and portfolio project: detectors, write-ups, derived visuals. ✅ |
| 1.2.1 | Do not edit, distort, distribute, reproduce, sell, or provide the data to any third party. | Raw files stay in the git-ignored `data/`. Tests use synthetic, hand-built events. Golden snapshots store Regista's derived output (cards, counts, event identifiers), never copied provider records. A public replay viewer must not embed raw event files. ✅ |
| 1.2.2 | Do not commercially exploit the data **or any analysis derived from it**. | No paid product, subscription, or commercial API. Anything tuned or trained on this data (thresholds, an expected-threat grid) must be re-derived from licensed data before any commercial use. ✅ |
| 1.2.4 | Do not publish material that might be defamatory or damaging to any individual or organisation. | Cards describe observations neutrally, never intent or blame (AGENTS.md). ✅ |
| 1.4 | Accredit any publication of analysis with the StatsBomb brand logo. | Any published write-up, screenshot, or chart shows the StatsBomb logo plus "Data: StatsBomb". The README carries the text credit. Before the first public push, add the logo from StatsBomb's Media Pack (https://statsbomb.com/media-pack/) to the README, because `docs/assets/3773497-shot-locations.svg` is derived analysis. ⚠️ Logo pending until publishing |
| 2.2 | StatsBomb asks users to register their name and email at https://www.statsbomb.com/resource-centre. | That link currently routes to Hudl's commercial StatsBomb product page, with no open-data registration form (see note below). Not applicable until a working form exists; do not use the sales form. |
| 7 | The data is StatsBomb's property; no transfer, distribution, or licensing without written consent. | Covered by the 1.2.1 practices above. ✅ |
| 6.1 | StatsBomb may suspend access at any time. | Providers stay behind adapters; the local copy is for development only. |

Agreement text checked against Regista's planned use on 2026-09-26: compatible.

### Compliance checklist
- [x] StatsBomb Public Data User Agreement reviewed (confirmed by Kassahun, 2026-09-26)
- [x] Open data source documented
- [x] Attribution requirement documented
- [ ] StatsBomb logo added before publishing StatsBomb-derived analysis
- [ ] Commercial rights obtained before monetization

> **Note:** StatsBomb's current open-data documentation still references `statsbomb.com/resource-centre` for registration, but that URL currently routes into Hudl's commercial StatsBomb site (checked 2026-09-26: it lands on `hudl.com/en_gb/products/statsbomb`) rather than an obvious open-data registration form. Regista uses the open data under the published agreement and does not fill in the sales form.

## What is public and what is not

| Public in this repository | Never committed |
|---|---|
| Source code and detectors | Raw provider files (`data/`) |
| Tests with synthetic, hand-built events | Databases built from provider data (`*.duckdb`) |
| Derived visuals and write-ups, with the StatsBomb logo | Copies or excerpts of raw event files |
| Documentation | |

## If Regista ever becomes commercial

Replace StatsBomb Open Data with a provider whose written agreement permits the intended commercial use, and re-derive any thresholds or models from that data, before any paid feature exists.

## Not used

- Transfermarkt and FBref: never scraped.
- Player photos, club crests, league logos.
