# Instructions for Coding Agents

Last updated: 2026-09-28

## Scope discipline
- Work only on the current milestone of the product track or the active research item in ROADMAP.md (two tracks, owner decision 2026-09-28). Stop and check in after each increment or milestone.
- Features enter the product only by promotion from research; unpromoted card types ship labeled "experimental" or not at all. See [STATUS.md](STATUS.md).
- Do not add features, dependencies, or abstractions for later milestones or phases.
- Stack choices live in [docs/STACK.md](docs/STACK.md); changing one is a recorded decision, not a drive-by.

## Working style
- Explain the reasoning behind each step.
- Leave the application working after every change: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pyright` pass.
- Write out full words in names and documentation; avoid abbreviations.
- Every document carries a `Last updated: YYYY-MM-DD` line under its title. Update it whenever the document changes.
- when doing reserach make sure to add a confidence score
-validate when you can

## Commits
- Agents may make commits, but only under the repository owner's git identity. Never change `git config user.*`.
- Never add a `Co-Authored-By` trailer for an AI assistant, and never add "Generated with Claude Code" or similar lines to commits or pull requests. No AI tool should appear as an author, co-author, or committer.
- Enforced by the empty `attribution` setting in `.claude/settings.json` and a local `.git/hooks/commit-msg` check that rejects AI co-author trailers. The git hook is not versioned; recreate it after a fresh clone.

## Architecture invariants
- Ports and adapters: domain code never imports provider formats. `cli.py` is the composition root.
- Detectors decide; templates render. A language model may only rephrase template output.
- Every insight carries supporting event identifiers and sources.
- Keep original provider records alongside normalized events.

## Leakage rules
- Detectors may only read events at or before the current replay position.
- No match-wide aggregates (for example "match high") computed from the full file.
- Matches are split into development, validation, and test (rule in [docs/specs/phase-2-data-model.md](docs/specs/phase-2-data-model.md)). Explore, invent metrics, and tune thresholds on development only. Compare detector variants on validation. Touch test only for a final estimate, never while developing.
- Splits are frozen and versioned (`splits/v<N>.json`). Never edit a split; a change is a new version with its reason recorded.
- Analytical tables summarize whole matches. In-match detectors never read them for the match being replayed, and "normal for this team" baselines use only matches that kicked off earlier.
- Detectors read only fields known at the event, or shortly after it (`known_at_event` or `delayed` in the Phase 2 specification). Fields known only in hindsight (for example `play_pattern`, pass assist flags, possession grouping, forward links between events) are for retrospective research only. A field whose timing is unclear counts as hindsight.
- What happened after a moment (for example, shots following a shift) may be studied and used as an evaluation target. It never feeds a card shown at that moment.
- Research runs against development data only: the development warehouse, and raw files of development matches. Never open validation or test matches while developing, whether through a database, a raw file, or a script.
- Context facts must have been published before the match's kickoff and are frozen at kickoff. Timestamped in-match updates require an explicit roadmap decision.
- The prefix-invariance test must always pass.

## Data rules
- StatsBomb Open Data is used only for non-commercial research and portfolio work unless I record separate written commercial rights. Do not build paid access, advertising, sponsorship, client delivery, or any other monetization on it.
- Never commit or publicly expose StatsBomb raw datasets, provider payloads, or databases containing them, including full event exports in a different schema. Public tests use synthetic fixtures.
- Public StatsBomb-derived analysis, cards, visualizations, and screenshots say "Data: StatsBomb" and carry the official logo, inside anything that can circulate on its own.
- Before a public release or any monetization, stop and have me re-check the license, registration process, and attribution guidance (see [DATA_SOURCES.md](DATA_SOURCES.md)).
- Never scrape Transfermarkt or FBref.
- No player photos, club crests, or league logos. Provider attribution that a license requires (for example "Data: StatsBomb" with the StatsBomb logo) is allowed.
- Never commit raw provider files or databases built from them. See [DATA_SOURCES.md](DATA_SOURCES.md).
- Injury wording: sourced history only, never medical inference.

## Research notes
- Any exploratory finding that could change a detector is written up as a research note from [docs/research/TEMPLATE.md](docs/research/TEMPLATE.md). It states the question, exact definitions, dataset, split, and code versions, the queries or calculations, sample size and exclusions, counterexamples and alternative explanations, and the decision.
- Agents may search for patterns and propose explanations. They never substitute their own judgment for the owner's judgment of fan usefulness.

## Ownership (never invent these)
I own: labeled evaluation moments, fan-usefulness judgments (including probe judgments), curated player context and injury records, source claims, and license confirmations. If one is needed, leave a clearly marked placeholder and ask.
- Agents may research and summarize license terms, but must never mark a personal confirmation, review, registration, or acceptance as done on my behalf, even when asked to "fill the gaps." Leave the box unchecked and tell me.

## Testing
- Every detector ships with a test for a firing case, a quiet case, and a suppression case.
- Contract tests pin provider assumptions (coordinates, sides, completion status).

## Locked definitions
Record metric definitions here as they are decided. Full detector specifications live in `docs/specs/`.
- Phase 1 detector: [docs/specs/phase-1-attacking-side-shift.md](docs/specs/phase-1-attacking-side-shift.md) (status: initial defaults to evaluate; since 2026-09-28 a team is evaluated only at its own final-third entries).
- Phase 2 attacking burst: [docs/specs/phase-2-attacking-burst.md](docs/specs/phase-2-attacking-burst.md) (status: candidate under owner review; penalties never count as shots).
- Phase 2 data model, corpus, and splits: [docs/specs/phase-2-data-model.md](docs/specs/phase-2-data-model.md) (status: development warehouse implemented for 800 development matches; held-out warehouse and `team_window_distributions` still design).
- Final-third entry: an open-play completed pass or carry starting before x = 80 and ending at or beyond x = 80 (attacking frame).
- Completed pass: the provider record has no outcome. Any recorded outcome, including "Unknown", means not completed; Regista never claims a completion the provider cannot confirm (match 3773497 has 4 "Unknown" passes). Carries always count as completed.
- Open play: decided per event from the pass type. Corner, Free Kick, Throw-in, Goal Kick, and Kick Off passes are set pieces and excluded. Recovery and Interception passes are open play. Carries always count. Never use the possession-level `play_pattern` for this: it labels whole possessions and may be assigned with hindsight.
- Channels: from the entry's end location; left y < 80/3, center 80/3 ≤ y ≤ 160/3, right y > 160/3. Low y is the acting team's left (checked on match 3773497; pinned by the contract test `test_low_y_is_the_acting_teams_left`).
- Channel shift: only an increase in a channel's share produces a candidate card. Decreases appear only as supporting evidence. An increase split across two channels that reaches the threshold in neither produces no card.
- Field tilt (Phase 2 metric): a team's completed open-play passes starting at x ≥ 80 in its own attacking frame, divided by both teams' such passes in the same window. No value when the combined count is below a minimum (set in Phase 2). Whether it becomes its own detector depends on replay evaluation.

# Some information
- Treat documented, settled project decisions as final unless new evidence directly contradicts them