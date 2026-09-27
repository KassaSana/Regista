"""Read the development warehouse safely: research connections, fingerprints, quality reports."""

from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb

LAYERS = ("normalized", "analytical")
# Wall-clock columns legitimately differ between otherwise identical builds.
_VOLATILE_COLUMNS = {("normalized", "ingest_runs"): ("started_at", "finished_at")}


def connect_research(path: Path) -> duckdb.DuckDBPyConnection:
    """Open a read-only connection that cannot read files outside the warehouse.

    External access cannot be re-enabled on an open connection, so held-out raw
    files stay unreachable through it.
    """
    return duckdb.connect(str(path), read_only=True, config={"enable_external_access": False})


def fingerprint(path: Path) -> dict[str, tuple[int, str]]:
    """Return each table's row count and an order-independent content hash.

    Two builds from the same raw files and code must produce identical fingerprints.
    Hashes are comparable only under the same DuckDB version (recorded in ``ingest_runs``).
    """
    result: dict[str, tuple[int, str]] = {}
    with connect_research(path) as connection:
        tables = connection.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema IN ('normalized', 'analytical') ORDER BY ALL"
        ).fetchall()
        for schema, table in tables:
            volatile = _VOLATILE_COLUMNS.get((schema, table))
            source = f"{schema}.{table}"
            if volatile:
                source = f"(SELECT * EXCLUDE ({', '.join(volatile)}) FROM {source})"
            row = connection.execute(
                f"SELECT count(*), coalesce(sum(hash(t::VARCHAR)), 0)::VARCHAR FROM {source} AS t"
            ).fetchone()
            assert row is not None
            count, total = int(row[0]), str(row[1])
            result[f"{schema}.{table}"] = (count, hashlib.sha256(total.encode()).hexdigest()[:16])
    return result


def snapshot_facts(path: Path) -> tuple[dict[str, object], int, dict[str, tuple[int, str]]]:
    """Return the ingest run, the count of non-development matches, and the fingerprint.

    A warehouse is safe to store remotely only when every match is development
    under the split recorded inside it.
    """
    with connect_research(path) as connection:
        # Timestamps as text: returning TIMESTAMPTZ values to Python would need pytz.
        cursor = connection.execute(
            "SELECT * REPLACE (started_at::VARCHAR AS started_at, "
            "finished_at::VARCHAR AS finished_at) FROM normalized.ingest_runs"
        )
        names = [column[0] for column in cursor.description or ()]
        rows = cursor.fetchall()
        if len(rows) != 1:
            raise ValueError(f"expected one ingest run in {path}, found {len(rows)}")
        run: dict[str, object] = dict(zip(names, rows[0], strict=True))
        outside = connection.execute(
            "SELECT count(*) FROM normalized.matches AS m "
            "LEFT JOIN normalized.splits AS s USING (match_id) "
            "WHERE s.bucket IS DISTINCT FROM 'development'"
        ).fetchone()
    assert outside is not None
    return run, int(outside[0]), fingerprint(path)


def quality_report(path: Path) -> tuple[str, dict[str, object]]:
    """Summarize data-quality results as Markdown and as a JSON-ready dictionary."""
    with connect_research(path) as connection:
        run = connection.execute(
            "SELECT ingest_run_id, source_commit, split_version, git_commit, git_dirty, "
            "finished_at::VARCHAR FROM normalized.ingest_runs"
        ).fetchone()
        assert run is not None
        statuses = dict(
            connection.execute(
                "SELECT dq_status, count(*) FROM normalized.matches GROUP BY ALL ORDER BY ALL"
            ).fetchall()
        )
        checks = connection.execute(
            "SELECT check_name, severity, count(*) FILTER (WHERE passed), "
            "count(*) FILTER (WHERE NOT passed) FROM normalized.dq_checks "
            "GROUP BY ALL ORDER BY severity, check_name"
        ).fetchall()
        failures = connection.execute(
            "SELECT match_id, check_name, severity, detail FROM normalized.dq_checks "
            "WHERE NOT passed ORDER BY severity, check_name, match_id"
        ).fetchall()
    lines = [
        "# Data-quality report",
        "",
        f"- Ingest run: `{run[0]}` (git `{run[3][:12]}`{', dirty' if run[4] else ''}), "
        f"finished {run[5]}",
        f"- Source commit: `{run[1]}`; split version {run[2]}",
        "- Matches by status: "
        + ", ".join(f"{status}: {count}" for status, count in statuses.items()),
        "",
        "| Check | Severity | Passed | Failed |",
        "|---|---|---:|---:|",
        *(f"| {name} | {severity} | {ok} | {bad} |" for name, severity, ok, bad in checks),
        "",
        "## Failures",
        "",
        *(
            f"- {match_id} `{check}` ({severity}): {detail}"
            for match_id, check, severity, detail in failures
        ),
    ]
    if not failures:
        lines.append("None.")
    summary: dict[str, object] = {
        "ingest_run_id": run[0],
        "source_commit": run[1],
        "split_version": run[2],
        "statuses": statuses,
        "checks": [
            {"check": name, "severity": severity, "passed": ok, "failed": bad}
            for name, severity, ok, bad in checks
        ],
        "failures": [
            {"match_id": match_id, "check": check, "severity": severity, "detail": detail}
            for match_id, check, severity, detail in failures
        ],
    }
    return "\n".join(lines) + "\n", summary
