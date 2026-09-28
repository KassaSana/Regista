# Phase 3 specification: Recorded match facts

Last updated: 2026-09-28

Status: provisional separate replay stream. The facts are mechanically
supported; usefulness and combined-stream redundancy remain to be judged.

## Inputs and timing

The StatsBomb adapter extracts provider-neutral details from three event types:
`Starting XI`, `Substitution`, and `Tactical Shift`. A starting event carries
its recorded formation and eleven named players. A substitution carries its
departing and entering players. A shift carries its recorded formation.
These fields are known at the event; the starting lineup is available before
kickoff. Detectors never inspect the original provider record.

Events are replayed in provider sequence. The fact detector retains only the
last recorded formation, its event identifier, and its source for each team.
Future events cannot change an earlier fact.

## Observations

| Record | Candidate sentence | Evidence | Rule |
|---|---|---|---|
| Starting XI | Team started in a recorded shape | Starting event and eleven players | One per recorded starting event |
| Substitution | Entering player replaced departing player | Substitution event | One per recorded substitution; omit provider reason |
| Tactical Shift | Recorded formation changed from A to B | Previous and current formation events | Only if B differs from the team's most recent recorded formation |

A shift with no earlier recorded formation is retained as the latest state but
produces no comparison sentence. A shift repeating the previous formation is
also quiet. It may contain player-position changes; this version does not claim
to explain those. Facts never say a substitution caused a formation change, a
coach intended something, or an injury occurred.

The source event identifiers and source names accompany every fact. Starting
player names are shown in the evidence view. Formation strings are formatted
with separators for display (for example `4231` becomes `4-2-3-1`) without
changing the recorded digits.

## Exposure and evaluation

`regista replay --match <id> --facts` displays this candidate stream. `--evidence`
adds the source events and starting-player list. The default replay continues
to show only the Phase 1 side-shift detector. The streams will be considered
together after the owner viewing probe; the Phase 3 gate is not passed by a
mechanical correctness check.

Synthetic tests cover a firing case for each fact, quiet events, repeated-shape
suppression, team isolation, evidence, and prefix invariance. The adapter is
checked against all 800 development matches, never validation or test matches.
