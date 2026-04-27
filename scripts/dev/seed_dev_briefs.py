"""Seed the Mac dev stack's briefs directory from a static 30-site fixture.

Reads the domain list from ``config/dev_dataset.json`` (committed), copies
each matching brief from ``data/output/briefs/`` (the production-pipeline
output, also committed) into ``data/dev/briefs/`` so the dev API container's
``BRIEFS_HOST_DIR`` bind-mount serves only fixture data.

This closes one of the four bind-mount leaks identified during M37
finalisation: the dev API was rendering 1,179 production briefs instead of
the 30 chosen for DEV.

Fail-loud: if any listed domain is missing a brief on disk, all missing
domains are collected and a single error is raised at the end. A partial
seed is never produced.

Idempotent: the destination directory is cleared of stray ``*.json`` files
before each run, so dropping a domain from the dataset removes it from
``data/dev/briefs/`` automatically.

Usage
-----
    python -m scripts.dev.seed_dev_briefs              # regenerate dev briefs
    python -m scripts.dev.seed_dev_briefs --check      # verify only, no writes
    python -m scripts.dev.seed_dev_briefs \\
        --dataset config/dev_dataset.json \\
        --briefs-dir data/output/briefs \\
        --dest-dir data/dev/briefs
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DATASET = _PROJECT_ROOT / "config" / "dev_dataset.json"
_DEFAULT_BRIEFS_DIR = _PROJECT_ROOT / "data" / "output" / "briefs"
_DEFAULT_DEST_DIR = _PROJECT_ROOT / "data" / "dev" / "briefs"


class SeedError(RuntimeError):
    """Raised when the seed cannot produce a consistent dev briefs set."""


@dataclass
class SeedReport:
    """Result of a seed or check run."""

    campaign: str
    dataset_path: Path
    briefs_dir: Path
    dest_dir: Path
    total_domains: int = 0
    copied: int = 0
    pruned: int = 0
    missing: list[tuple[str, str]] = field(default_factory=list)
    mode: str = "write"

    def summary(self) -> str:
        lines = [
            f"campaign={self.campaign}",
            f"mode={self.mode}",
            f"dataset={self.dataset_path}",
            f"briefs={self.briefs_dir}",
            f"dest={self.dest_dir}",
            f"total_domains={self.total_domains}",
            f"missing={len(self.missing)}",
        ]
        if self.mode == "write":
            lines.append(f"copied={self.copied} pruned={self.pruned}")
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
    """Map (bucket, domain) → source brief path. Separate found vs missing.

    Raises SeedError if the dataset's buckets have zero domains in total.
    A run that succeeded against an empty dataset would silently prune the
    dev fixture to nothing, which is never the intended outcome.
    """
    resolved: list[tuple[str, str, Path]] = []
    missing: list[tuple[str, str]] = []
    for bucket, domains in dataset["buckets"].items():
        for domain in domains:
            brief_path = briefs_dir / f"{domain}.json"
            if brief_path.is_file():
                resolved.append((bucket, domain, brief_path))
            else:
                missing.append((bucket, domain))
    if not resolved and not missing:
        raise SeedError(
            f"Dataset has zero domains across all buckets — refusing to "
            f"prune the dev fixture to empty. Check {dataset.get('campaign', '<unknown>')}."
        )
    return resolved, missing


def _prune_dest(dest_dir: Path, expected_filenames: set[str]) -> int:
    """Remove stray *.json files from dest_dir not in the expected set.

    Returns the number of files removed. Non-JSON files are left alone
    (so a hypothetical README in data/dev/briefs/ is not blown away).
    """
    pruned = 0
    if not dest_dir.is_dir():
        return 0
    for child in dest_dir.iterdir():
        if child.is_file() and child.suffix == ".json" and child.name not in expected_filenames:
            child.unlink()
            pruned += 1
    return pruned


def run_seed(
    dataset_path: Path = _DEFAULT_DATASET,
    briefs_dir: Path = _DEFAULT_BRIEFS_DIR,
    dest_dir: Path = _DEFAULT_DEST_DIR,
    check_only: bool = False,
) -> SeedReport:
    """Run the seed operation.

    Args:
        dataset_path: Path to the JSON dataset file.
        briefs_dir:   Source briefs directory (production pipeline output).
        dest_dir:     Destination briefs directory (dev fixture).
        check_only:   If True, verify briefs without writing.

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
        dest_dir=dest_dir,
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
        logger.info("dev_fixture_seed_briefs_check_ok {}", report.summary())
        return report

    dest_dir.mkdir(parents=True, exist_ok=True)
    expected = {f"{domain}.json" for _bucket, domain, _src in resolved}
    report.pruned = _prune_dest(dest_dir, expected)

    for _bucket, domain, src in resolved:
        dst = dest_dir / f"{domain}.json"
        shutil.copyfile(src, dst)
        report.copied += 1

    logger.info("dev_fixture_seed_briefs_complete {}", report.summary())
    return report


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="seed_dev_briefs",
        description="Seed data/dev/briefs/ from the dev fixture domain list.",
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
        help="Source briefs directory (default: data/output/briefs).",
    )
    parser.add_argument(
        "--dest-dir",
        type=Path,
        default=_DEFAULT_DEST_DIR,
        help="Destination briefs directory (default: data/dev/briefs).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify source briefs exist without copying.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = run_seed(
            dataset_path=args.dataset,
            briefs_dir=args.briefs_dir,
            dest_dir=args.dest_dir,
            check_only=args.check,
        )
    except SeedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    verb = "checked" if args.check else "seeded"
    print(
        f"{verb} {report.total_domains} brief(s) | "
        f"campaign={report.campaign} | "
        f"copied={report.copied} pruned={report.pruned}"
    )
    return 0


if __name__ == "__main__":
    os.chdir(_PROJECT_ROOT)
    raise SystemExit(main())
