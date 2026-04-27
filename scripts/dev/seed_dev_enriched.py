"""Seed the Mac dev stack's enriched companies.db from a static 30-site fixture.

Filters the production ``data/enriched/companies.db`` down to rows whose
domain appears in ``config/dev_dataset.json`` and writes the result to
``data/dev/enriched/companies.db``. The dev compose then bind-mounts that
fixture DB at the canonical ``/data/enriched/`` path, so the scheduler in
DEV uses the same code path as PROD without touching production rows.

Closes the second of the four bind-mount leaks identified during M37
finalisation: the dev scheduler was reading 1,173 production company rows
and worked around the leak with a HEIMDALL_DEV_DATASET env-var override.
With this fixture in place the env-var workaround can be retired.

Tables copied:
  - ``companies`` — the canonical row per CVR.
  - ``domains``   — the per-domain rollup the scheduler joins against.

Tables intentionally NOT copied:
  - ``enrichment_log`` — audit/debug history, not load-bearing for dev.
  - ``sqlite_sequence`` — sqlite internal, auto-managed.

Schema preservation: copies CREATE TABLE + CREATE INDEX statements verbatim
from the source DB so any future schema change in the enrichment pipeline
flows through without a script update.

Fail-loud: every fixture domain must be present in the source DB. Partial
seeds raise SeedError without writing the destination.

Idempotent: the destination DB (and its WAL/SHM siblings) are wiped before
each run.

Usage
-----
    python -m scripts.dev.seed_dev_enriched              # regenerate dev DB
    python -m scripts.dev.seed_dev_enriched --check      # verify only, no writes
    python -m scripts.dev.seed_dev_enriched \\
        --dataset config/dev_dataset.json \\
        --source data/enriched/companies.db \\
        --dest data/dev/enriched/companies.db
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DATASET = _PROJECT_ROOT / "config" / "dev_dataset.json"
_DEFAULT_SOURCE_DB = _PROJECT_ROOT / "data" / "enriched" / "companies.db"
_DEFAULT_DEST_DB = _PROJECT_ROOT / "data" / "dev" / "enriched" / "companies.db"

# Tables we replicate. enrichment_log + sqlite_sequence are intentionally
# excluded — the scheduler reads companies + domains, nothing else.
_COPY_TABLES = ("companies", "domains")


class SeedError(RuntimeError):
    """Raised when the seed cannot produce a consistent dev enriched DB."""


@dataclass
class SeedReport:
    """Result of a seed or check run."""

    dataset_path: Path
    source_db: Path
    dest_db: Path
    total_domains: int = 0
    companies_copied: int = 0
    domains_copied: int = 0
    missing_in_companies: list[str] = field(default_factory=list)
    missing_in_domains: list[str] = field(default_factory=list)
    mode: str = "write"

    def summary(self) -> str:
        lines = [
            f"mode={self.mode}",
            f"dataset={self.dataset_path}",
            f"source={self.source_db}",
            f"dest={self.dest_db}",
            f"total_domains={self.total_domains}",
            f"missing_companies={len(self.missing_in_companies)}",
            f"missing_domains={len(self.missing_in_domains)}",
        ]
        if self.mode == "write":
            lines.append(
                f"companies_copied={self.companies_copied} "
                f"domains_copied={self.domains_copied}"
            )
        return " ".join(lines)


def _load_fixture_domains(path: Path) -> list[str]:
    """Return the flat list of domains from config/dev_dataset.json."""
    if not path.is_file():
        raise SeedError(f"Dataset file not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "buckets" not in data:
        raise SeedError(f"Dataset missing 'buckets' key: {path}")
    domains: list[str] = []
    for _bucket, items in data["buckets"].items():
        domains.extend(items)
    if not domains:
        raise SeedError(f"Dataset has no domains: {path}")
    return domains


def _missing_domains(conn: sqlite3.Connection, table: str, domains: list[str]) -> list[str]:
    """Return the subset of domains absent from <table>.domain."""
    missing: list[str] = []
    for d in domains:
        row = conn.execute(
            f"SELECT 1 FROM {table} WHERE domain = ? LIMIT 1", (d,)
        ).fetchone()
        if row is None:
            missing.append(d)
    return missing


def _reset_db_file(db_path: Path) -> None:
    """Delete the dev enriched DB and its WAL/SHM siblings if present."""
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{db_path}{suffix}")
        if candidate.exists():
            candidate.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)


def _copy_schema(src: sqlite3.Connection, dst: sqlite3.Connection) -> None:
    """Copy CREATE TABLE / CREATE INDEX statements for the replicated tables."""
    rows = src.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE type IN ('table', 'index') AND sql IS NOT NULL "
        "ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END, name"
    ).fetchall()
    for _type, _name, tbl_name, sql in rows:
        if tbl_name not in _COPY_TABLES:
            continue
        dst.execute(sql)


def _copy_filtered_rows(
    src: sqlite3.Connection,
    dst: sqlite3.Connection,
    table: str,
    domains: list[str],
) -> int:
    """Copy rows from src.<table> where domain IN (...) into dst.<table>.

    Returns the number of rows copied.
    """
    cols = [r[1] for r in src.execute(f"PRAGMA table_info({table})").fetchall()]
    col_list = ", ".join(cols)
    placeholders = ", ".join("?" for _ in cols)
    domain_placeholders = ", ".join("?" for _ in domains)

    src_rows = src.execute(
        f"SELECT {col_list} FROM {table} WHERE domain IN ({domain_placeholders})",
        domains,
    ).fetchall()

    dst.executemany(
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
        src_rows,
    )
    return len(src_rows)


def run_seed(
    dataset_path: Path = _DEFAULT_DATASET,
    source_db: Path = _DEFAULT_SOURCE_DB,
    dest_db: Path = _DEFAULT_DEST_DB,
    check_only: bool = False,
) -> SeedReport:
    """Run the seed operation.

    Args:
        dataset_path: Path to the JSON dataset file.
        source_db:    Source enriched DB (production output).
        dest_db:      Destination dev enriched DB.
        check_only:   If True, verify presence without writing.

    Returns:
        A ``SeedReport`` describing the outcome.

    Raises:
        SeedError: If the source DB or any fixture domain is missing.
    """
    domains = _load_fixture_domains(dataset_path)

    if not source_db.is_file():
        raise SeedError(f"Source enriched DB not found: {source_db}")

    report = SeedReport(
        dataset_path=dataset_path,
        source_db=source_db,
        dest_db=dest_db,
        total_domains=len(domains),
        mode="check" if check_only else "write",
    )

    src = sqlite3.connect(source_db, timeout=10)
    try:
        report.missing_in_companies = _missing_domains(src, "companies", domains)
        report.missing_in_domains = _missing_domains(src, "domains", domains)

        if report.missing_in_companies or report.missing_in_domains:
            details = []
            if report.missing_in_companies:
                details.append(
                    f"  companies: {', '.join(report.missing_in_companies)}"
                )
            if report.missing_in_domains:
                details.append(
                    f"  domains: {', '.join(report.missing_in_domains)}"
                )
            raise SeedError(
                "Fixture domains absent from source enriched DB:\n"
                + "\n".join(details)
            )

        if check_only:
            logger.info("dev_fixture_seed_enriched_check_ok {}", report.summary())
            return report

        _reset_db_file(dest_db)
        dst = sqlite3.connect(dest_db, timeout=10)
        try:
            with dst:
                _copy_schema(src, dst)
                report.companies_copied = _copy_filtered_rows(
                    src, dst, "companies", domains
                )
                report.domains_copied = _copy_filtered_rows(
                    src, dst, "domains", domains
                )
                # Normalise the operational-gate columns to "fixture-ready"
                # state. Inheriting prod flags (e.g. ready_for_scan=0 on a
                # prod row that's been quarantined) would silently shrink the
                # dev pipeline below the 30-domain count the dataset
                # promises. Whatever the prod state, dev runs all 30.
                dst.execute("UPDATE domains SET ready_for_scan = 1")
        finally:
            dst.close()
    finally:
        src.close()

    logger.info("dev_fixture_seed_enriched_complete {}", report.summary())
    return report


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="seed_dev_enriched",
        description="Seed data/dev/enriched/companies.db from the dev fixture.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=_DEFAULT_DATASET,
        help="Path to the dev dataset JSON (default: config/dev_dataset.json).",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=_DEFAULT_SOURCE_DB,
        help="Source enriched DB (default: data/enriched/companies.db).",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=_DEFAULT_DEST_DB,
        help="Destination dev enriched DB (default: data/dev/enriched/companies.db).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify source contains all fixture domains without writing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = run_seed(
            dataset_path=args.dataset,
            source_db=args.source,
            dest_db=args.dest,
            check_only=args.check,
        )
    except SeedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    verb = "checked" if args.check else "seeded"
    print(
        f"{verb} {report.total_domains} domain(s) | "
        f"companies_copied={report.companies_copied} "
        f"domains_copied={report.domains_copied}"
    )
    return 0


if __name__ == "__main__":
    os.chdir(_PROJECT_ROOT)
    raise SystemExit(main())
