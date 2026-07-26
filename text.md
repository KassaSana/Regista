# Soccer Player Rating Engine — Plan

## Scope

**What this is:** a system that consumes match event data, assigns a value to every action a player takes, aggregates those values into a per-match performance rating, and explains the rating in terms of what the player did well and badly relative to others in their position.

**Minimum viable product boundary:** one completed match, one competition, ratings and explanations printed to the terminal. No user interface, no live feed, no video, no database.

**Explicitly not in the minimum viable product:** live streams, player recognition from video, tactical analysis, match prediction, web frontend, authentication, deployment. Every one of these is a real goal and every one of them is downstream of a working valuation layer.

The reason for drawing the line here is simple: if the ratings are wrong, nothing built on top of them matters. If the ratings are right, everything else is a delivery problem with known solutions.

---

## Data Foundation

The minimum viable product runs on StatsBomb open data — the `statsbomb/open-data` repository on GitHub. It is free, event-level, and covers full competitions including La Liga seasons.

The structure you will be working against:

| File | Contains |
|------|----------|
| `competitions.json` | Every available competition and season, with identifiers |
| `matches/{competition_id}/{season_id}.json` | All matches in a season, with match identifiers |
| `lineups/{match_id}.json` | Both squads, with player identifiers, jersey numbers, and positions |
| `events/{match_id}.json` | Every event in the match, in chronological order |

An individual event carries a type (pass, shot, carry, duel, pressure, interception, and so on), the team and player responsible, a pitch location, a timestamp, and a type-specific object holding the details that matter for that type. Shots carry a StatsBomb expected goals value already computed, which is useful as both a feature and a sanity check.

Pitch coordinates run 120 units along the length and 80 across the width, with each team's events oriented so that they attack toward increasing length. Confirm this against the specification document in the repository before you write any spatial logic — getting the orientation wrong will silently invert every conclusion you draw, and it will look plausible the whole time.

**A choice to make early:** load the raw files yourself, or use the `statsbombpy` package. Loading raw gives you full understanding of the schema, which matters because you will be reasoning about it constantly. The package saves a day. Given that the point of this project is partly to understand soccer better, I lean toward raw for the first pass — but it is a defensible call either way.

---

## Architecture

Five modules with clean boundaries between them. The boundaries matter more than the internals, because the valuation module is going to get replaced and you want that swap to cost nothing.

```
ingest → normalize → value → aggregate → explain
```

**Ingest.** Reads raw match files from disk. Knows about StatsBomb file layout and nothing else. Its entire job is to hand back a list of raw event dictionaries plus a lineup.

Why isolate this: when you later add a live event feed from a different provider, only this module changes.

**Normalize.** Converts provider-specific events into your own internal event representation. This is the single most important boundary in the system.

Your internal event should be provider-agnostic and carry roughly:

```
Event
  event_id
  match_id
  period, minute, second
  team_id, player_id
  position          # the position the player was occupying at this moment
  action_type       # your own enum, not StatsBomb's
  start_location    # (length, width) in your own coordinate convention
  end_location      # optional — passes and carries have one, tackles do not
  outcome           # success / failure / neutral
  under_pressure    # boolean
  possession_id     # groups events into one team's spell of possession
  raw               # keep the original dictionary for anything you have not modeled yet
```

The `raw` passthrough is deliberate. You will repeatedly discover a field you need three weeks in, and you do not want to re-ingest to get it.

Your `action_type` enum should be smaller than StatsBomb's event taxonomy. Collapse aggressively at first — pass, carry, shot, dribble, defensive action, turnover, aerial duel is enough to start. Expanding the enum later is easy; a sprawling enum you do not understand is not.

**Value.** Takes a sequence of normalized events and attaches a numeric value to each one. This is where the intelligence lives, and it is the module you will rewrite.

Version zero is a lookup table. Version one is a learned possession-value model. Both satisfy the same interface:

```
value(events: list[Event]) -> list[ValuedEvent]
```

Note the signature takes the whole sequence, not one event. The learned version needs context — what came before, what state the game was in — and if you design the interface around single events you will have to break it later.

**Aggregate.** Rolls valued events up to a per-player-per-match rating. Handles the two adjustments that make ratings comparable at all: minutes played and position.

**Explain.** Compares a player's aggregated profile against positional baselines and emits statements about strengths and weaknesses. Needs a corpus of matches to build baselines from, so it depends on having run the pipeline across a season, not a single game.

---

## The Valuation Layer

### Version zero — weighted heuristic

Every action type gets a base value, modified by pitch location and outcome. Something like:

```
value = base_value[action_type]
      × location_multiplier(start_location, end_location)
      × outcome_modifier(outcome)
```

Starting weights to argue with — these are opinions, not facts, and you should expect to change them:

| Action | Base value | Notes |
|--------|-----------|-------|
| Goal | +1.00 | Anchor everything else to this |
| Shot on target, no goal | ? | Should this be positive at all, or is expected goals the right value? |
| Successful pass | +0.01 | Deliberately tiny — most passes are unremarkable |
| Pass into the penalty area | ? | Fill this in yourself and justify the ratio to a plain pass |
| Ball recovery | +0.05 | Scale by pitch location — recovering high is worth far more |
| Turnover | −0.08 | Scale by location — losing it in your own third is much worse |
| Successful tackle | +0.06 | |
| Foul conceded | ? | Depends heavily on where; near your own box this is close to conceding a shot |

The gaps are intentional. Deciding what a pass into the box is worth relative to a plain pass forces you to state a theory of the game, which is the actual point of the exercise.

The location multiplier is the part that does the real work. A rough starting shape: value scales with how close the action moves the ball toward the opponent's goal, weighted more heavily in central areas than wide ones. You will want to look at how expected threat grids are constructed before finalizing this.

**Why bother with a heuristic you know is inferior:** it gives you a complete working pipeline in days rather than weeks, and it gives you a baseline to measure the learned model against. Without a baseline you cannot tell whether the learned model is good or merely complicated.

### Version one — learned possession value

Train a model that estimates, from the current game state, the probability the team in possession scores before possession changes hands. The value of an action is the change in that probability across the action.

This handles your original list — goals, recoveries, passes, turnovers — under one consistent rule instead of a dozen hand-tuned constants. A turnover is negative automatically, because possession value transfers to the opponent. A recovery high up the pitch is worth more than one in your own box, automatically, because the resulting state is more dangerous.

Features to start from: ball location, distance and angle to goal, time remaining in possession, number of actions in the possession so far, whether the action was under pressure. Gradient-boosted trees are the right first model — fast to train, handles the tabular shape naturally, and you can inspect feature importance to check the model learned something sensible rather than something spurious.

Label construction is the part people get wrong. Define carefully what counts as "this possession ended in a goal," including how you handle possessions that end at halftime, and be consistent about it.

---

## Rating Aggregation

Raw summed value is not a rating. Two adjustments stand between them.

**Minutes.** Express contributions per ninety minutes so a substitute who played twenty minutes is not compared against a player who played the full match on raw totals. Applies to the component statistics; whether the headline rating itself should be a rate or a total is a real design question — a total rewards playing well for longer, which is arguably correct.

**Position.** A center back and a winger generate value through completely different actions. Comparing their raw sums ranks positions, not players. The fix is to compute percentile rank within position group: this center back's ball progression versus all center backs, not versus all players.

This means the rating is inherently relative, and it means you need a corpus. A single match cannot produce a meaningful positional percentile. Plan to process a full season before the explanation layer produces anything trustworthy.

Position groups to start with — goalkeeper, center back, fullback, defensive midfielder, central midfielder, attacking midfielder, winger, forward. Eight is probably too coarse and sixteen is too granular given sample sizes. Somewhere in between is right, and where exactly depends on how much data you end up with.

**An open question worth thinking about:** should the output be a single number on a familiar scale, or a profile across several dimensions? A single number is legible and immediately comparable. A profile is more honest, because "how good was this performance" genuinely is multidimensional. You could produce both — the profile is what you actually computed, the single number is a weighted collapse of it.

---

## Explanation Layer

Once positional baselines exist, explanation is largely arithmetic. For each player, compute their percentile within position across a set of action categories: ball progression, chance creation, ball retention under pressure, defensive recovery, aerial duels, shot quality.

Strengths are categories in the top band. Weaknesses are categories in the bottom band. Match-specific commentary comes from comparing the player's performance in this match against their own season baseline — that is what separates "this player is bad at retaining the ball" from "this player had an unusually careless game."

Template-driven text output is enough at first, and it is more trustworthy than generated prose because you can trace every sentence back to a number.

---

## Phased Todo

### Phase 0 — Foundation

- [ ] Clone the StatsBomb open data repository and confirm which competitions and seasons are available
- [ ] Read the event specification document in the repository — actually read it, do not skim
- [ ] Verify the pitch coordinate convention empirically: plot shot locations for one match and confirm they cluster where you expect
- [ ] Pick one match you have actually watched, and keep using it for the whole project
- [ ] Set up the project with Poetry, pytest, and a source layout
- [ ] Decide: raw file loading or `statsbombpy`

### Phase 1 — Ingest and Normalize

- [ ] Load one match's events and lineup into memory
- [ ] Define the internal `Event` representation
- [ ] Write the normalizer from StatsBomb events to internal events
- [ ] Define your `action_type` enum, starting deliberately small
- [ ] Handle possession grouping — verify possession identifiers behave the way you assume
- [ ] Write tests against known events in your chosen match: a specific goal, a specific substitution, a specific red card if there is one
- [ ] Count events by type and sanity check the totals against what you remember of the match

### Phase 2 — Heuristic Valuation

- [ ] Define the `value()` interface
- [ ] Build the base weight table, filling in the gaps left above
- [ ] Implement the location multiplier
- [ ] Implement the outcome modifier
- [ ] Produce a valued event stream for one match
- [ ] Print the ten highest-valued and ten lowest-valued actions of the match — do these match your memory of what mattered?

That last item is the real test of Phase 2. If the highest-valued actions are not the ones you remember, either your weights are wrong or your understanding of the match is, and finding out which is the whole point.

### Phase 3 — Aggregation and First Ratings

- [ ] Sum valued events per player
- [ ] Add minutes-played handling, including substitutions
- [ ] Produce a per-player rating table for one match
- [ ] Compare against your own opinion of who played well
- [ ] Iterate on weights until the ratings stop being obviously wrong
- [ ] Run across a full season and store results
- [ ] Introduce PostgreSQL once holding a season in memory becomes annoying, and not before

### Phase 4 — Positional Normalization and Explanation

- [ ] Define position groups
- [ ] Compute per-position, per-category distributions across the season
- [ ] Convert raw values to positional percentiles
- [ ] Build the category taxonomy for explanations
- [ ] Write the template-based explanation generator
- [ ] Generate explanations for the starting eleven of your test match and read them critically
- [ ] Identify where the explanations say something obviously false, and trace back to which layer caused it

### Phase 5 — Learned Valuation

- [ ] Construct the training dataset: game states with possession outcome labels
- [ ] Define state features
- [ ] Train a gradient-boosted model on possession-scoring probability
- [ ] Validate it properly — hold out entire matches, not random events, or you will leak information across the split
- [ ] Inspect feature importance and confirm it learned something sensible
- [ ] Implement the learned valuer behind the existing `value()` interface
- [ ] Compare learned ratings against heuristic ratings — where do they disagree most, and who is right?

That final comparison is worth writing up properly. The disagreements are where you learn the most about both models.

### Phase 6 — Interface

- [ ] Design the read API contract
- [ ] Spring Boot service exposing match ratings, player profiles, and explanations
- [ ] React and TypeScript frontend: match view, player view, comparison view
- [ ] Visualize action values spatially — a pitch map of where a player generated and lost value

### Phase 7 — Tactical Analysis

- [ ] Average position by phase of play
- [ ] Pass network construction and visualization
- [ ] Possession-win location distributions as a pressing proxy
- [ ] Detect within-match shifts: compare structure before and after the hour mark, or before and after a substitution
- [ ] Compare the same manager across matches to characterize their approach

This is a sibling module to the rating engine, not an extension of it. It reads the same normalized events and produces entirely different output.

### Phase 8 — Live

- [ ] Survey live event feed providers and their terms, latency, and free tiers
- [ ] Build a second ingest adapter for the chosen feed
- [ ] Make the valuation layer incremental so it updates as events arrive rather than reprocessing
- [ ] Streaming updates to the frontend
- [ ] Build the manual tagging companion as the zero-cost fallback — and possibly build it regardless, because tagging a match by hand will teach you more about soccer than the rest of this project combined

### Phase 9 — Video

Deferred indefinitely, for the reasons already discussed. If you return to it, the honest version is not "process a Peacock stream" but "train a player detection and tracking model on an existing labeled dataset and see how far you get." Treat it as a separate computer vision project that happens to share a domain.

---

## Decisions Deferred

**Database.** In-memory and Parquet files are fine until a season of valued events becomes unwieldy. PostgreSQL when that happens, not before.

**Rating scale.** Whether the headline output is a familiar ten-point scale, a percentile, or something else. Decide after you have seen the distribution of raw values.

**Multiple competitions.** Whether ratings should be comparable across La Liga and the Premier League, or normalized within each. This is a genuinely hard question about league strength and you should not touch it until the single-league version works.

**Deployment.** Irrelevant until there is something worth deploying.

**Authentication.** Irrelevant until someone other than you uses it.

---

## What To Build First

Phase 0 and Phase 1, ending at a script that loads your chosen match, normalizes every event, and prints a count by action type alongside a chronological list of every event involving one specific player.

Not ratings. Not valuation. Just proof that you can turn a raw match file into a clean internal representation and that the representation matches what actually happened on the pitch. Everything above rests on that being correct, and it is the cheapest thing in the project to verify.