# Data Sources

Regista's code is public. Provider data is not: it is downloaded locally into `data/` and never committed.

## StatsBomb Open Data

- Source: https://github.com/hudl/open-data (the old `github.com/statsbomb/open-data` address redirects here).
- Governing agreement: *StatsBomb Public Data User Agreement*, https://github.com/hudl/open-data/blob/master/LICENSE.pdf (last updated 8 September 2023).
- Open data needs no authentication or paid license. The paid StatsBomb API is a separate commercial product.
- Accurate description of our status: "Regista uses StatsBomb Open Data subject to the StatsBomb Public Data User Agreement." Never write "licensed by StatsBomb" or imply endorsement.
- Compliance record last checked: 2026-09-26.

### What the agreement says, and how Regista complies

Clauses were read by a coding agent from the official PDF (all five pages) on 2026-09-26. This summary is research, not legal advice, and not Kassahun's personal review.

| Clause | Requirement | Regista's practice |
|---|---|---|
| Preamble, 1.1 | For analysis, research, and shared understanding; analysis and conclusions may be shared publicly. | Non-commercial learning and portfolio project. |
| 1.2.1 | Do not edit, distort, distribute, reproduce, sell, or provide the data to any third party. | Raw files stay in git-ignored `data/`. Public tests use synthetic fixtures only. Golden snapshots store derived output only. No public raw-data download, API, or near-complete event export, even in a changed schema. Users are pointed to the official repository instead. |
| 1.2.2 | Do not commercially exploit the data **or any analysis derived from it**. | No paid access, subscriptions, advertising or sponsorship, client work, or insight API without written commercial rights. Thresholds and models built on this data are re-derived from licensed data before any commercial use. |
| 1.2.4 | Do not publish material that might be defamatory or damaging to any individual or organisation. | Cards describe observations neutrally, never intent or blame. |
| 1.4 | Accredit any publication of analysis with the StatsBomb brand logo. | "Data: StatsBomb" plus the official logo on every published analysis. Any image or card that can circulate on its own carries its own attribution. Logo source: the Media Pack linked from the repository README (https://statsbomb.com/media-pack/, which opens Hudl's asset library); usage guidance at https://brand.hudl.com. Never recreate, recolor, or crop the logo. |
| 2.2 | StatsBomb asks users to register their name and email via the Resource Centre. | Requested by official documentation (statsbombpy, StatsBombR) but **not currently actionable**: the documented URL redirects to Hudl's commercial product page (see note). |
| 6.1 | StatsBomb may suspend access at any time. | Providers stay behind adapters; the local copy is for development only. |
| 7 | The data is StatsBomb's property; no transfer, distribution, or licensing without written consent. | Covered by the 1.2.1 practices. |

> **Note (checked 2026-09-26):** The statsbombpy and StatsBombR documentation still asks Open Data users to register at `https://www.statsbomb.com/resource-centre`. That URL currently redirects to `https://www.hudl.com/en_gb/products/statsbomb`, Hudl's commercial product page, whose form is for the sales team. It exposes no identifiable Open Data registration form. Regista does not submit the sales form to satisfy this instruction.

### Status

Human-owned items (only Kassahun ticks these):
- [ ] Kassahun personally read the current StatsBomb Public Data User Agreement (`LICENSE.pdf`).
- [ ] If an official Open Data registration form becomes available, Kassahun registers his own name and email.
- [ ] Before the first public release, Kassahun re-checks the agreement, the registration path, and the brand guidance, and records the date here.
- [ ] Written Hudl/StatsBomb commercial rights are obtained before any monetization involving StatsBomb data or derived analysis.

Recorded by research (agent):
- [x] Official source and governing agreement recorded.
- [x] Raw-data policy recorded: no committing, redistributing, or publicly exposing StatsBomb raw files, provider payloads, or databases containing them.
- [x] Regista is currently a non-commercial research and portfolio project (ROADMAP.md).
- [x] Attribution requirement recorded.
- [x] Registration URL checked on 2026-09-26 (see note).
- [ ] Official StatsBomb logo added before the first public StatsBomb-derived analysis or visualization.

## What is public and what is not

| Public in this repository | Never committed or exposed |
|---|---|
| Source code and detectors | Raw provider files (`data/`) |
| Tests with synthetic, hand-built events | Databases built from provider data (`*.duckdb`) |
| Derived insights, aggregates, and visuals, with attribution and logo | Copies or excerpts of raw event files, or full event exports in any schema |
| Documentation | |

## If Regista ever becomes commercial

Obtain written terms from Hudl/StatsBomb first (commercial product page: https://www.hudl.com/en_gb/products/statsbomb), or replace StatsBomb Open Data with a provider whose written agreement permits the intended use. Re-derive any thresholds or models from licensed data before any paid feature exists.

## Not used

- Transfermarkt and FBref: never scraped.
- Player photos, club crests, league logos.
