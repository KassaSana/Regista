# Increment 1: Foundation

This increment establishes the toolchain and the place where Regista will be
assembled. It deliberately contains no soccer rules yet.

## Why use a `src/` layout?

With the package under `src/regista`, running Python from the repository root
cannot accidentally import an uninstalled `regista` directory. Tests exercise
the package as the environment installs it, so missing packaging configuration
is exposed early instead of appearing only after release.

## What is the composition root?

The composition root is the single place that chooses concrete implementations
and connects them. For Regista, that is `regista.cli`.

Later increments will define abstract ports for loading events, valuing actions,
aggregating ratings, and explaining results. File loaders and heuristic valuers
will be concrete adapters. Only the composition root should need to know which
adapter was chosen:

```text
CLI composition root
  -> StatsBomb file source
  -> normalizer
  -> heuristic valuer
  -> match aggregator
  -> provisional explainer
```

This keeps the domain independent of command-line parsing, files, HTTP clients,
and terminal formatting. A future live source or learned valuer can replace one
choice at the root without changing the domain.
