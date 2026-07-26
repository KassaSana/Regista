# Regista

Regista turns soccer match events into explainable, position-aware player ratings.
The current implementation includes the project foundation and domain geometry from the
[rating-engine plan](regista_rating_engine_156f9116.plan.md).

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

## Architecture

Application code uses a `src/` layout. The future rating pipeline will follow:

```text
ingest -> normalize -> value -> aggregate -> explain
```

`regista.cli` is the composition root: the one module that will choose and wire
the concrete implementations behind those boundaries.
