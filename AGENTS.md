# Instructions for Coding Agents

## Scope discipline
- Work only on the current phase in ROADMAP.md. Stop and check in after each increment.
- Do not add features, dependencies, or abstractions for future phases.
- Stack choices live in [docs/STACK.md](docs/STACK.md); changing one is a recorded decision, not a drive-by.

## Working style
- Explain the reasoning behind each step.
- Occasionally leave small, clearly marked implementation gaps (`# TODO(Kassahun): ...`) for me to fill in.
- Learning gaps must never leave the application broken: `uv run pytest`, `uv run ruff check .`, and `uv run pyright` still pass. Raise `NotImplementedError` or mark the test as skipped; never leave invalid code.
- Write out full words in names and documentation; avoid abbreviations.

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
- Thresholds are tuned on development matches only; never inspect evaluation matches while tuning.
- Context facts must have been published before the match's kickoff and are frozen at kickoff. Timestamped in-match updates require an explicit roadmap decision.
- The prefix-invariance test must always pass.

## Data rules
- StatsBomb open data: development only, attribution required, no commercial use.
- Never scrape Transfermarkt or FBref.
- No player photos, club crests, or league logos. Provider attribution that a license requires (for example "Data: StatsBomb" with the StatsBomb logo) is allowed.
- Never commit raw provider files or databases built from them. See [DATA_SOURCES.md](DATA_SOURCES.md).
- Injury wording: sourced history only, never medical inference.

## Ownership (never invent these)
I own: labeled evaluation moments, curated player context and injury records, source claims, and license confirmations. If one is needed, leave a clearly marked placeholder and ask.

## Testing
- Every detector ships with a test for a firing case, a quiet case, and a suppression case.
- Contract tests pin provider assumptions (coordinates, sides, completion status).

## Locked definitions
Record metric definitions here as they are decided. Full detector specifications live in `docs/specs/`.
- Phase 1 detector: [docs/specs/phase-1-attacking-side-shift.md](docs/specs/phase-1-attacking-side-shift.md) (status: initial defaults to evaluate).
- Final-third entry: an open-play completed pass or carry starting before x = 80 and ending at or beyond x = 80 (attacking frame).
- Open play: decided per event from the pass type. Corner, Free Kick, Throw-in, Goal Kick, and Kick Off passes are set pieces and excluded. Recovery and Interception passes are open play. Carries always count. Never use the possession-level `play_pattern` for this: it labels whole possessions and may be assigned with hindsight.
- Channels: from the entry's end location; left y < 80/3, center 80/3 ≤ y ≤ 160/3, right y > 160/3. Which side is "left" is to be confirmed by the contract test.
- Channel shift: only an increase in a channel's share produces a candidate card. Decreases appear only as supporting evidence. An increase split across two channels that reaches the threshold in neither produces no card.
- Field tilt (Phase 2 metric): a team's completed open-play passes starting at x ≥ 80 in its own attacking frame, divided by both teams' such passes in the same window. No value when the combined count is below a minimum (set in Phase 2). Whether it becomes its own detector depends on replay evaluation.