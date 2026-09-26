# Regista

Regista is a match companion for soccer fans. It replays a match in time order,
notices when something meaningful changes, explains it in one plain sentence,
and shows the evidence behind it.

The current implementation includes the project foundation and domain geometry.
See [ROADMAP.md](ROADMAP.md) for the phases and [AGENTS.md](AGENTS.md) for the
working rules. The Phase 1 detector is specified in
[docs/specs/phase-1-attacking-side-shift.md](docs/specs/phase-1-attacking-side-shift.md).

## Development

Regista requires Python 3.13 and uses `uv` for its environment and lockfile.

```console
uv sync
uv run regista
uv run pytest
uv run ruff check .
uv run pyright
```

Provider data belongs under `data/` and is intentionally excluded from version
control.

The coordinate contract expects the StatsBomb open-data repository at
`data/statsbomb/`. It skips when that local provider fixture is unavailable.
StatsBomb open data is used for development only, with attribution, and not
commercially. See [DATA_SOURCES.md](DATA_SOURCES.md).

Data: StatsBomb (https://github.com/hudl/open-data).

## Architecture

Application code uses a `src/` layout. The Phase 1 pipeline will follow:

```text
load -> normalize -> replay -> detect -> render template -> card with evidence
```

`regista.cli` is the composition root: the one module that will choose and wire
the concrete implementations behind those boundaries.
