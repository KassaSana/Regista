# Increment 17: Read-only Wikidata coach-tenure research

Last updated: 2026-09-28

## Scope

Add a bounded Wikidata SPARQL adapter and a command that prints unreviewed
head-coach tenure candidates for one validated team Q identifier. The adapter
keeps statement links, references, date values and precision, and retrieval
time. It cannot write to the source-claim store. See [research note 10](../research/10-wikidata-coach-candidates.md).

## Verification

Five synthetic adapter tests passed. A live query was not run because an
identifiable User-Agent contact has not been supplied; none is fabricated.
The full suite reported 283 passed with no skips. Ruff lint and format checks
passed after formatting the touched files, and strict Pyright reported zero
errors.
