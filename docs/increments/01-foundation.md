# Increment 1: Foundation

Last updated: 2026-09-27

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

Later increments define the ports for loading events, detecting insights, and
rendering them. The StatsBomb file loader is a concrete adapter. Only the
composition root needs to know which one was chosen:

```text
CLI composition root
  -> StatsBomb event file loader and normalizer   (increment 3)
  -> replay engine                                (increment 4)
  -> attacking-side shift detector                (increment 4)
  -> template                                     (increment 4)
```

This keeps the domain independent of command-line parsing, files, HTTP clients,
and terminal formatting. A future live source can replace one choice at the
root without changing the domain.
