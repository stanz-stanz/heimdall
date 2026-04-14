"""Seed the Mac dev stack's clients.db with a static 30-site fixture.

Reads the domain list from ``config/dev_dataset.json`` (committed), loads
each matching brief from ``data/output/briefs/``, and inserts it into the
prospects table of a fresh ``data/dev/clients.db``.

This script is the local equivalent of what the prospecting pipeline does in
production, but pinned to a curated 30-domain fixture so the dev stack is
reproducible from one run to the next. The dev DB is NOT committed; it is
regenerated on demand via ``make dev-seed``.

Fail-loud: if any listed domain is missing a brief on disk, all missing
domains are collected and a single error is raised at the end. A partial
seed is never produced.

Usage
-----
    python -m scripts.dev.seed_dev_db             # regenerate dev DB
    python -m scripts.dev.seed_dev_db --check     # verify briefs only, no writes
    python -m scripts.dev.seed_dev_db \\
        --db-path data/dev/clients.db \\
        --dataset config/dev_dataset.json \\
        --briefs-dir data/output/briefs
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

from src.db.connection import init_db
from src.outreach.promote import insert_prospect

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DATASET = _PROJECT_ROOT / "config" / "dev_dataset.json"
_DEFAULT_BRIEFS_DIR = _PROJECT_ROOT / "data" / "output" / "briefs"
_DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "dev" / "clients.db"


class SeedError(RuntimeError):
    """Raised when the seed cannot produce a consistent dev dataset."""


@dataclass
class SeedReport:
    """Result of a seed or check run."""

    campaign: str
    dataset_path: Path
    briefs_dir: Path
    db_path: Path
    total_domains: int = 0
    inserted: int = 0
    skipped: int = 0
    missing: list[tuple[str, str]] = field(default_factory=list)
    mode: str = "write"

    def summary(self) -> str:
        lines = [
            f"campaign={self.campaign}",
            f"mode={self.mode}",
            f"dataset={self.dataset_path}",
            f"briefs={self.briefs_dir}",
            f"db={self.db_path}",
            f"total_domains={self.total_domains}",
            f"missing={len(self.missing)}",
        ]
        if self.mode == "write":
            lines.append(f"inserted={self.inserted} skipped={self.skipped}")
        return " ".join(lines)


def _load_dataset(path: Path) -> dict:
    if not path.is_file():
        raise SeedError(f"Dataset file not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SeedError(f"Dataset root must be an object: {path}")
    if "campaign" not in data or "buckets" not in data:
        raise SeedError(f"Dataset missing required keys 'campaign'/'buckets': {path}")
    return data


def _resolve_brief_paths(
    dataset: dict, briefs_dir: Path
) -> tuple[list[tuple[str, str, Path]], list[tuple[str, str]]]:
    """Map (bucket, domain) → brief path. Separate found vs missing."""
    resolved: list[tuple[str, str, Path]] = []
    missing: list[tuple[str, str]] = []
    for bucket, domains in dataset["buckets"].items():
        for domain in domains:
            brief_path = briefs_dir / f"{domain}.json"
            if brief_path.is_file():
                resolved.append((bucket, domain, brief_path))
            else:
                missing.append((bucket, domain))
    return resolved, missing


def _load_brief(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        brief = json.load(f)
    if not isinstance(brief, dict):
        raise SeedError(f"Brief must be a JSON object: {path}")
    if not brief.get("domain"):
        raise SeedError(f"Brief missing 'domain' key: {path}")
    return brief


def _reset_db_file(db_path: Path) -> None:
    """Delete the dev DB and its WAL/SHM siblings if present."""
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{db_path}{suffix}")
        if candidate.exists():
            candidate.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)


def run_seed(
    dataset_path: Path = _DEFAULT_DATASET,
    briefs_dir: Path = _DEFAULT_BRIEFS_DIR,
    db_path: Path = _DEFAULT_DB_PATH,
    check_only: bool = False,
) -> SeedReport:
    """Run the seed operation.

    Args:
        dataset_path: Path to the JSON dataset file.
        briefs_dir:   Path to the briefs directory.
        db_path:      Path to the dev SQLite database.
        check_only:   If True, verify briefs without writing the DB.

    Returns:
        A ``SeedReport`` describing the outcome.

    Raises:
        SeedError: If any listed domain has no brief on disk.
    """
    dataset = _load_dataset(dataset_path)
    resolved, missing = _resolve_brief_paths(dataset, briefs_dir)

    report = SeedReport(
        campaign=dataset["campaign"],
        dataset_path=dataset_path,
        briefs_dir=briefs_dir,
        db_path=db_path,
        total_domains=len(resolved) + len(missing),
        missing=missing,
        mode="check" if check_only else "write",
    )

    if missing:
        formatted = "\n".join(f"  - {b}/{d}" for b, d in missing)
        raise SeedError(
            f"{len(missing)} brief file(s) missing for dataset "
            f"{dataset_path}:\n{formatted}"
        )

    if check_only:
        logger.info("seed_check_ok {}", report.summary())
        return report

    _reset_db_file(db_path)
    conn = init_db(str(db_path))
    try:
        for _bucket, _domain, brief_path in resolved:
            brief = _load_brief(brief_path)
            try:
                insert_prospect(conn, dataset["campaign"], brief)
                report.inserted += 1
            except sqlite3.IntegrityError:
                report.skipped += 1
    finally:
        conn.close()

    logger.info("seed_complete {}", report.summary())
    return report


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="seed_dev_db",
        description="Seed the dev stack clients.db from a static fixture.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=_DEFAULT_DATASET,
        help="Path to the dev dataset JSON (default: config/dev_dataset.json).",
    )
    parser.add_argument(
        "--briefs-dir",
        type=Path,
        default=_DEFAULT_BRIEFS_DIR,
        help="Path to the briefs directory (default: data/output/briefs).",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=_DEFAULT_DB_PATH,
        help="Path to the dev SQLite DB (default: data/dev/clients.db).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify briefs exist without writing the dev DB.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = run_seed(
            dataset_path=args.dataset,
            briefs_dir=args.briefs_dir,
            db_path=args.db_path,
            check_only=args.check,
        )
    except SeedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    verb = "checked" if args.check else "seeded"
    print(
        f"{verb} {report.total_domains} domain(s) | "
        f"campaign={report.campaign} | "
        f"inserted={report.inserted} skipped={report.skipped}"
    )
    return 0


if __name__ == "__main__":
    os.chdir(_PROJECT_ROOT)
    raise SystemExit(main())
