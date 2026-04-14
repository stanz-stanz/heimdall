"""Tests for scripts/dev/seed_dev_db.py.

Validates the fail-loud missing-brief behavior, the wipe-and-recreate
semantics, and the --check dry mode. All tests use ``tmp_path`` so the
real ``data/dev/clients.db`` is never touched.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.dev.seed_dev_db import (
    SeedError,
    SeedReport,
    _parse_args,
    main,
    run_seed,
)


def _write_brief(path: Path, domain: str, findings: list[dict] | None = None) -> None:
    """Write a minimal brief JSON that passes promote.insert_prospect."""
    path.write_text(
        json.dumps(
            {
                "domain": domain,
                "cvr": "00000000",
                "company_name": domain.split(".")[0].title(),
                "bucket": "A",
                "industry_code": "5610",
                "industry": "Restaurant",
                "technology": {"cms": "WordPress", "hosting": "Cloudflare"},
                "findings": findings or [],
            }
        ),
        encoding="utf-8",
    )


def _write_dataset(
    path: Path,
    buckets: dict[str, list[str]],
    campaign: str = "dev-fixture",
) -> None:
    path.write_text(
        json.dumps({"campaign": campaign, "buckets": buckets}),
        encoding="utf-8",
    )


@pytest.fixture
def fixture_layout(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Build a minimal dataset + brief directory + dev DB path under tmp."""
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    dataset_path = tmp_path / "dev_dataset.json"
    db_path = tmp_path / "dev" / "clients.db"

    _write_dataset(
        dataset_path,
        {
            "wordpress": ["alpha.dk", "beta.dk"],
            "shopify": ["gamma.dk"],
        },
    )
    for domain in ("alpha.dk", "beta.dk", "gamma.dk"):
        _write_brief(briefs_dir / f"{domain}.json", domain)

    return dataset_path, briefs_dir, db_path


def test_run_seed_writes_dev_db(fixture_layout: tuple[Path, Path, Path]) -> None:
    dataset_path, briefs_dir, db_path = fixture_layout

    report = run_seed(dataset_path, briefs_dir, db_path, check_only=False)

    assert isinstance(report, SeedReport)
    assert report.mode == "write"
    assert report.total_domains == 3
    assert report.inserted == 3
    assert report.skipped == 0
    assert report.missing == []
    assert db_path.is_file()

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT domain, campaign FROM prospects ORDER BY domain"
        ).fetchall()
    finally:
        conn.close()

    assert rows == [
        ("alpha.dk", "dev-fixture"),
        ("beta.dk", "dev-fixture"),
        ("gamma.dk", "dev-fixture"),
    ]


def test_run_seed_is_idempotent(fixture_layout: tuple[Path, Path, Path]) -> None:
    """Second run wipes and recreates, not double-inserts."""
    dataset_path, briefs_dir, db_path = fixture_layout

    run_seed(dataset_path, briefs_dir, db_path, check_only=False)
    second = run_seed(dataset_path, briefs_dir, db_path, check_only=False)

    assert second.inserted == 3
    assert second.skipped == 0

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0]
    finally:
        conn.close()

    assert count == 3


def test_run_seed_check_only_does_not_write(
    fixture_layout: tuple[Path, Path, Path],
) -> None:
    dataset_path, briefs_dir, db_path = fixture_layout

    report = run_seed(dataset_path, briefs_dir, db_path, check_only=True)

    assert report.mode == "check"
    assert report.total_domains == 3
    assert report.inserted == 0
    assert not db_path.exists()


def test_run_seed_fails_loud_on_missing_brief(
    fixture_layout: tuple[Path, Path, Path],
) -> None:
    dataset_path, briefs_dir, db_path = fixture_layout
    (briefs_dir / "beta.dk.json").unlink()
    (briefs_dir / "gamma.dk.json").unlink()

    with pytest.raises(SeedError) as excinfo:
        run_seed(dataset_path, briefs_dir, db_path)

    msg = str(excinfo.value)
    assert "2 brief file(s) missing" in msg
    assert "beta.dk" in msg
    assert "gamma.dk" in msg
    assert not db_path.exists()


def test_run_seed_missing_dataset_file(tmp_path: Path) -> None:
    with pytest.raises(SeedError, match="Dataset file not found"):
        run_seed(
            dataset_path=tmp_path / "nope.json",
            briefs_dir=tmp_path,
            db_path=tmp_path / "dev.db",
        )


def test_run_seed_malformed_dataset(tmp_path: Path) -> None:
    dataset_path = tmp_path / "bad.json"
    dataset_path.write_text('{"campaign": "x"}', encoding="utf-8")

    with pytest.raises(SeedError, match="missing required keys"):
        run_seed(
            dataset_path=dataset_path,
            briefs_dir=tmp_path,
            db_path=tmp_path / "dev.db",
        )


def test_cli_main_success(
    fixture_layout: tuple[Path, Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    dataset_path, briefs_dir, db_path = fixture_layout

    rc = main(
        [
            "--dataset",
            str(dataset_path),
            "--briefs-dir",
            str(briefs_dir),
            "--db-path",
            str(db_path),
        ]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "seeded 3 domain(s)" in out
    assert "inserted=3" in out


def test_cli_main_check(
    fixture_layout: tuple[Path, Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    dataset_path, briefs_dir, db_path = fixture_layout

    rc = main(
        [
            "--dataset",
            str(dataset_path),
            "--briefs-dir",
            str(briefs_dir),
            "--db-path",
            str(db_path),
            "--check",
        ]
    )

    assert rc == 0
    assert not db_path.exists()
    assert "checked 3 domain(s)" in capsys.readouterr().out


def test_cli_main_missing_brief_returns_nonzero(
    fixture_layout: tuple[Path, Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    dataset_path, briefs_dir, db_path = fixture_layout
    (briefs_dir / "alpha.dk.json").unlink()

    rc = main(
        [
            "--dataset",
            str(dataset_path),
            "--briefs-dir",
            str(briefs_dir),
            "--db-path",
            str(db_path),
        ]
    )

    assert rc == 1
    err = capsys.readouterr().err
    assert "alpha.dk" in err
    assert not db_path.exists()


def test_parse_args_defaults() -> None:
    ns = _parse_args([])
    assert ns.dataset.name == "dev_dataset.json"
    assert ns.briefs_dir.name == "briefs"
    assert ns.db_path.name == "clients.db"
    assert ns.check is False
