# Research note: Wikidata coach-tenure candidate workflow

Last updated: 2026-09-28

## Question

Can a bounded, read-only query surface head-coach tenure statements with enough
provenance and date precision for later owner review, without treating them as
confirmed historical context?

## Definitions

The workflow requests Wikidata [head coach (P286)](https://www.wikidata.org/wiki/Property:P286)
statements for one validated team Q identifier. It retains the Wikidata
statement URI, coach item and label, optional start and end values with their
precision, optional [reference URL (P854)](https://www.wikidata.org/wiki/Property:P854),
and retrieval timestamp. Wikidata's start and end qualifiers are P580 and
P582; their time precision must be kept because a year-only value can render
as 1 January in a raw date value. See [Wikidata's qualifier help](https://www.wikidata.org/wiki/Help:Qualifiers)
and [query examples](https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service/queries).

A returned row is a **candidate**, not a `SourceClaim`. It lacks a reliable
publication timestamp for the underlying assertion and may lack a reference.
No automatic conversion or database write exists.

## Data

No live Wikidata statement was fetched or admitted in this increment. Tests
use only synthetic SPARQL JSON. The provider documentation was read from the
[official query-service manual](https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual),
[Wikidata query documentation](https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service/en),
and [Wikidata source guidance](https://www.wikidata.org/wiki/Help:Sources).
No validation or test match data is involved.

## Method

Set `REGISTA_WIKIDATA_USER_AGENT` to an identifiable contact string, then run
`uv run python scripts/research/wikidata_coach_tenures.py Q7156` to inspect one
team's candidates. The Q identifier in that example is FC Barcelona's item;
the command does not approve or store any returned assertion. The caller must
review entity identity, statement references, publication history, exact date
precision, and rights before proposing a curated claim.

The adapter makes one bounded HTTPS GET request to the official SPARQL
endpoint with a JSON Accept header, a 20-second network timeout, a 100-row
query limit, and a response-size limit. The official manual asks automated
clients to use a descriptive User-Agent and documents service limits. The
script requires its value rather than inventing the owner's contact details.

Point-in-time check: query results are current Wikidata state. Their retrieval
timestamp is recorded, but the query does not establish when a statement was
first published. A present-day result cannot become context for a past match
without independent evidence that Regista had recorded it before kickoff.

## Results

Five synthetic tests pass for query bounds, QID injection rejection, statement
and reference parsing, preservation of year versus day precision, unknown
dates, and the request headers. There is no live coverage or factual accuracy
estimate. The response parser does not collapse duplicate reference rows or
decide between conflicting statements; they remain visible for review.

## Counterexamples and alternative interpretations

- A P286 statement can have no reference, no start/end qualifiers, or only a
  year-level date. These cannot support an exact appointment-day claim.
- Query-service data is updated asynchronously, and current state can contain
  later corrections. Retrieval today does not prove publication before a
  historical match.
- A team QID must be verified against the intended Regista team; names alone
  can be ambiguous. A reference URL can point to a source that itself needs
  checking and license review.

## Confidence

These are judgmental evidence scores, not calibrated probabilities.

- **0.9:** the adapter rejects unvalidated QIDs and retains the structural
  fields present in the synthetic SPARQL response.
- **0.7:** the query shape follows official Wikidata documentation. It has not
  yet been executed against the live endpoint in this checkout.
- **Not assessed:** real statement coverage, accuracy, publication timing,
  owner approval, or fan usefulness.

## Owner judgment

No entity mapping or source claim has been approved. This section remains
owner-owned.

## Decision

Keep the workflow read-only. Live desk-checking with an owner-supplied
User-Agent and independent source review are required before any specific
coach tenure enters the source-claim store. No context card follows from this
increment.
