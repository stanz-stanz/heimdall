"""Tests for scripts/dev/seed_dev_enriched.py.

Validates schema preservation, row filtering, fail-loud behaviour, and the
--check dry mode. All tests use ``tmp_path`` so the real
``data/dev/enriched/companies.db`` is never touched.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.dev.seed_dev_enriched import (
    SeedError,
    SeedReport,
    main,
    run_seed,
)


def _build_source_db(
    path: Path,
    rows: list[tuple],
    domain_ready_overrides: dict[str, int] | None = None,
) -> None:
    """Create a minimal source enriched DB matching the prod schema shape.

    rows: list of (cvr, name, domain) tuples — the script copies any
    columns it finds, so we only need the columns the test relies on.
    domain_ready_overrides: optional per-domain ready_for_scan override
    (defaults to 1 if absent). Used to verify the dev fixture normalises
    operational-gate flags from prod's state.
    """
    overrides = domain_ready_overrides or {}
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE companies (
                cvr TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                domain TEXT DEFAULT '',
                contactable INTEGER DEFAULT 1
            );
            CREATE TABLE domains (
                domain TEXT PRIMARY KEY,
                cvr_count INTEGER DEFAULT 1,
                representative_cvr TEXT DEFAULT '',
                ready_for_scan INTEGER DEFAULT 1
            );
            CREATE TABLE enrichment_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cvr TEXT NOT NULL,
                step TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX idx_companies_domain ON companies(domain);
            CREATE INDEX idx_log_cvr ON enrichment_log(cvr);
            """
        )
        conn.executemany(
            "INSERT INTO companies (cvr, name, domain) VALUES (?, ?, ?)",
            rows,
        )
        conn.executemany(
            "INSERT INTO domains (domain, representative_cvr, ready_for_scan) VALUES (?, ?, ?)",
            [
                (d, c, overrides.get(d, 1))
                for c, _n, d in rows
                if d
            ],
        )
        # Plant audit-log noise that should NOT propagate to dev fixture.
        conn.execute(
            "INSERT INTO enrichment_log (cvr, step, created_at) VALUES (?, ?, ?)",
            ("00000001", "fetch", "2026-01-01T00:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()


def _write_dataset(path: Path, domains: list[str]) -> None:
    path.write_text(
        json.dumps(
            {
                "campaign": "dev-fixture",
                "buckets": {"only": domains},
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def fixture_layout(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Build a 4-row source DB + dataset selecting 2 of those rows."""
    source_db = tmp_path / "src" / "companies.db"
    source_db.parent.mkdir()
    dest_db = tmp_path / "dev" / "enriched" / "companies.db"
    dataset_path = tmp_path / "dev_dataset.json"

    _build_source_db(
        source_db,
        [
            ("00000001", "Alpha", "alpha.dk"),
            ("00000002", "Beta", "beta.dk"),
            ("00000003", "Gamma", "gamma.dk"),
            ("00000004", "Delta", "delta.dk"),
        ],
    )
    _write_dataset(dataset_path, ["alpha.dk", "gamma.dk"])

    return dataset_path, source_db, dest_db


def test_run_seed_writes_filtered_companies(
    fixture_layout: tuple[Path, Path, Path],
) -> None:
    dataset_path, source_db, dest_db = fixture_layout

    report = run_seed(dataset_path, source_db, dest_db, check_only=False)

    assert isinstance(report, SeedReport)
    assert report.mode == "write"
    assert report.total_domains == 2
    assert report.companies_copied == 2
    assert report.domains_copied == 2
    assert dest_db.is_file()

    conn = sqlite3.connect(dest_db)
    try:
        rows = conn.execute(
            "SELECT cvr, name, domain FROM companies ORDER BY cvr"
        ).fetchall()
        domain_rows = conn.execute("SELECT domain FROM domains ORDER BY domain").fetchall()
    finally:
        conn.close()

    assert rows == [("00000001", "Alpha", "alpha.dk"), ("00000003", "Gamma", "gamma.dk")]
    assert domain_rows == [("alpha.dk",), ("gamma.dk",)]


def test_run_seed_skips_enrichment_log(
    fixture_layout: tuple[Path, Path, Path],
) -> None:
    """enrichment_log is intentionally not replicated."""
    dataset_path, source_db, dest_db = fixture_layout

    run_seed(dataset_path, source_db, dest_db, check_only=False)

    conn = sqlite3.connect(dest_db)
    try:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        conn.close()

    assert "companies" in names
    assert "domains" in names
    assert "enrichment_log" not in names


def test_run_seed_normalises_ready_for_scan(tmp_path: Path) -> None:
    """Domains marked ready_for_scan=0 in prod become 1 in the dev fixture.

    The dev fixture's contract is "all 30 domains run in dev." Inheriting
    a prod ready_for_scan=0 quarantine flag would silently shrink the
    pipeline and contradict that contract.
    """
    source_db = tmp_path / "src.db"
    dest_db = tmp_path / "dst.db"
    dataset_path = tmp_path / "ds.json"

    _build_source_db(
        source_db,
        [
            ("00000001", "Alpha", "alpha.dk"),
            ("00000002", "Beta", "beta.dk"),
        ],
        domain_ready_overrides={"alpha.dk": 0, "beta.dk": 0},
    )
    _write_dataset(dataset_path, ["alpha.dk", "beta.dk"])

    run_seed(dataset_path, source_db, dest_db, check_only=False)

    conn = sqlite3.connect(dest_db)
    try:
        rows = conn.execute(
            "SELECT domain, ready_for_scan FROM domains ORDER BY domain"
        ).fetchall()
    finally:
        conn.close()

    assert rows == [("alpha.dk", 1), ("beta.dk", 1)]


def test_run_seed_preserves_indexes(
    fixture_layout: tuple[Path, Path, Path],
) -> None:
    dataset_path, source_db, dest_db = fixture_layout

    run_seed(dataset_path, source_db, dest_db, check_only=False)

    conn = sqlite3.connect(dest_db)
    try:
        idx_names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
            )
        }
    finally:
        conn.close()

    assert "idx_companies_domain" in idx_names
    # Indexes attached to skipped tables should not propagate.
    assert "idx_log_cvr" not in idx_names


def test_run_seed_is_idempotent(
    fixture_layout: tuple[Path, Path, Path],
) -> None:
    """Second run wipes and recreates, no row accumulation."""
    dataset_path, source_db, dest_db = fixture_layout

    run_seed(dataset_path, source_db, dest_db, check_only=False)
    second = run_seed(dataset_path, source_db, dest_db, check_only=False)

    assert second.companies_copied == 2

    conn = sqlite3.connect(dest_db)
    try:
        count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    finally:
        conn.close()
    assert count == 2


def test_run_seed_fails_loud_on_missing_company(tmp_path: Path) -> None:
    source_db = tmp_path / "companies.db"
    dest_db = tmp_path / "dev" / "companies.db"
    dataset_path = tmp_path / "ds.json"

    _build_source_db(source_db, [("00000001", "Alpha", "alpha.dk")])
    _write_dataset(dataset_path, ["alpha.dk", "ghost.dk"])

    with pytest.raises(SeedError, match="Fixture domains absent"):
        run_seed(dataset_path, source_db, dest_db, check_only=False)

    assert not dest_db.exists()


def test_run_seed_fails_loud_on_missing_source(tmp_path: Path) -> None:
    dataset_path = tmp_path / "ds.json"
    _write_dataset(dataset_path, ["alpha.dk"])

    with pytest.raises(SeedError, match="Source enriched DB not found"):
        run_seed(dataset_path, tmp_path / "missing.db", tmp_path / "dest.db")


def test_run_seed_fails_loud_on_missing_dataset(tmp_path: Path) -> None:
    with pytest.raises(SeedError, match="Dataset file not found"):
        run_seed(tmp_path / "missing.json", tmp_path / "src.db", tmp_path / "dst.db")


def test_run_seed_fails_loud_on_empty_dataset(tmp_path: Path) -> None:
    dataset_path = tmp_path / "ds.json"
    _write_dataset(dataset_path, [])

    with pytest.raises(SeedError, match="has no domains"):
        run_seed(dataset_path, tmp_path / "src.db", tmp_path / "dst.db")


def test_check_only_does_not_write(
    fixture_layout: tuple[Path, Path, Path],
) -> None:
    dataset_path, source_db, dest_db = fixture_layout

    report = run_seed(dataset_path, source_db, dest_db, check_only=True)

    assert report.mode == "check"
    assert report.companies_copied == 0
    assert report.domains_copied == 0
    assert not dest_db.exists()


def test_check_only_still_fails_on_missing(
    fixture_layout: tuple[Path, Path, Path],
) -> None:
    dataset_path, source_db, dest_db = fixture_layout
    _write_dataset(dataset_path, ["alpha.dk", "ghost.dk"])

    with pytest.raises(SeedError):
        run_seed(dataset_path, source_db, dest_db, check_only=True)


def test_main_returns_zero_on_success(
    fixture_layout: tuple[Path, Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    dataset_path, source_db, dest_db = fixture_layout

    rc = main(
        [
            "--dataset",
            str(dataset_path),
            "--source",
            str(source_db),
            "--dest",
            str(dest_db),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "seeded 2 domain(s)" in out
    assert "companies_copied=2" in out


def test_main_returns_one_on_missing(
    fixture_layout: tuple[Path, Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    dataset_path, source_db, dest_db = fixture_layout
    _write_dataset(dataset_path, ["alpha.dk", "ghost.dk"])

    rc = main(
        [
            "--dataset",
            str(dataset_path),
            "--source",
            str(source_db),
            "--dest",
            str(dest_db),
        ]
    )
    assert rc == 1
    assert "error:" in capsys.readouterr().err
