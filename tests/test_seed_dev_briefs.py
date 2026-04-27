"""Tests for scripts/dev/seed_dev_briefs.py.

Validates the fail-loud missing-brief behaviour, the prune-stray-files
idempotency contract, and the --check dry mode. All tests use ``tmp_path``
so the real ``data/dev/briefs/`` is never touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.dev.seed_dev_briefs import (
    SeedError,
    SeedReport,
    main,
    run_seed,
)


def _write_brief(path: Path, domain: str) -> None:
    """Write a minimal brief JSON. Schema only needs to round-trip via copy."""
    path.write_text(
        json.dumps({"domain": domain, "marker": "dev-fixture-test"}),
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
    """Build a minimal dataset + source brief directory + dest dir under tmp."""
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    dest_dir = tmp_path / "dev" / "briefs"
    dataset_path = tmp_path / "dev_dataset.json"

    _write_dataset(
        dataset_path,
        {
            "wordpress": ["alpha.dk", "beta.dk"],
            "shopify": ["gamma.dk"],
        },
    )
    for domain in ("alpha.dk", "beta.dk", "gamma.dk"):
        _write_brief(briefs_dir / f"{domain}.json", domain)

    return dataset_path, briefs_dir, dest_dir


def test_run_seed_copies_all_briefs(
    fixture_layout: tuple[Path, Path, Path],
) -> None:
    dataset_path, briefs_dir, dest_dir = fixture_layout

    report = run_seed(dataset_path, briefs_dir, dest_dir, check_only=False)

    assert isinstance(report, SeedReport)
    assert report.mode == "write"
    assert report.total_domains == 3
    assert report.copied == 3
    assert report.pruned == 0
    assert report.missing == []

    copied = sorted(p.name for p in dest_dir.glob("*.json"))
    assert copied == ["alpha.dk.json", "beta.dk.json", "gamma.dk.json"]

    # Round-trip check: contents preserved.
    payload = json.loads((dest_dir / "alpha.dk.json").read_text(encoding="utf-8"))
    assert payload["domain"] == "alpha.dk"
    assert payload["marker"] == "dev-fixture-test"


def test_run_seed_is_idempotent(
    fixture_layout: tuple[Path, Path, Path],
) -> None:
    """Second run overwrites, doesn't accumulate new files."""
    dataset_path, briefs_dir, dest_dir = fixture_layout

    run_seed(dataset_path, briefs_dir, dest_dir, check_only=False)
    second = run_seed(dataset_path, briefs_dir, dest_dir, check_only=False)

    assert second.copied == 3
    assert second.pruned == 0
    assert sorted(p.name for p in dest_dir.glob("*.json")) == [
        "alpha.dk.json",
        "beta.dk.json",
        "gamma.dk.json",
    ]


def test_run_seed_prunes_stray_json_files(
    fixture_layout: tuple[Path, Path, Path],
) -> None:
    """A *.json file in dest that isn't in the dataset is removed on next run."""
    dataset_path, briefs_dir, dest_dir = fixture_layout

    run_seed(dataset_path, briefs_dir, dest_dir, check_only=False)

    # Drop a stale file that simulates a domain previously in the fixture.
    stale = dest_dir / "removed-from-fixture.dk.json"
    stale.write_text("{}", encoding="utf-8")

    report = run_seed(dataset_path, briefs_dir, dest_dir, check_only=False)
    assert report.pruned == 1
    assert not stale.exists()


def test_run_seed_does_not_prune_non_json_files(
    fixture_layout: tuple[Path, Path, Path],
) -> None:
    """A README.md (or any non-*.json) in dest survives the prune."""
    dataset_path, briefs_dir, dest_dir = fixture_layout

    dest_dir.mkdir(parents=True, exist_ok=True)
    readme = dest_dir / "README.md"
    readme.write_text("dev fixture briefs", encoding="utf-8")

    run_seed(dataset_path, briefs_dir, dest_dir, check_only=False)
    assert readme.exists()


def test_run_seed_fails_loud_on_missing_brief(
    fixture_layout: tuple[Path, Path, Path],
) -> None:
    dataset_path, briefs_dir, dest_dir = fixture_layout

    # Remove one of the source briefs.
    (briefs_dir / "beta.dk.json").unlink()

    with pytest.raises(SeedError, match="1 brief file\\(s\\) missing"):
        run_seed(dataset_path, briefs_dir, dest_dir, check_only=False)

    # Dest dir must NOT have been created or populated by the failed run.
    assert not (dest_dir / "alpha.dk.json").exists()


def test_run_seed_fails_loud_lists_all_missing(
    fixture_layout: tuple[Path, Path, Path],
) -> None:
    dataset_path, briefs_dir, dest_dir = fixture_layout

    (briefs_dir / "alpha.dk.json").unlink()
    (briefs_dir / "gamma.dk.json").unlink()

    with pytest.raises(SeedError) as exc_info:
        run_seed(dataset_path, briefs_dir, dest_dir, check_only=False)

    msg = str(exc_info.value)
    assert "wordpress/alpha.dk" in msg
    assert "shopify/gamma.dk" in msg
    assert "2 brief file(s) missing" in msg


def test_check_only_does_not_write(
    fixture_layout: tuple[Path, Path, Path],
) -> None:
    dataset_path, briefs_dir, dest_dir = fixture_layout

    report = run_seed(dataset_path, briefs_dir, dest_dir, check_only=True)

    assert report.mode == "check"
    assert report.copied == 0
    assert report.pruned == 0
    assert not dest_dir.exists()


def test_check_only_still_fails_on_missing(
    fixture_layout: tuple[Path, Path, Path],
) -> None:
    dataset_path, briefs_dir, dest_dir = fixture_layout
    (briefs_dir / "beta.dk.json").unlink()

    with pytest.raises(SeedError):
        run_seed(dataset_path, briefs_dir, dest_dir, check_only=True)


def test_load_dataset_rejects_missing_keys(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"campaign": "x"}), encoding="utf-8")

    with pytest.raises(SeedError, match="missing required keys"):
        run_seed(bad, tmp_path, tmp_path / "dest")


def test_run_seed_rejects_empty_dataset(tmp_path: Path) -> None:
    """An empty buckets-dict must fail-loud, not silently prune the fixture."""
    dataset_path = tmp_path / "empty.json"
    dataset_path.write_text(
        json.dumps({"campaign": "test", "buckets": {}}),
        encoding="utf-8",
    )
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    # Plant a stale file to prove the seed doesn't prune it on the failure path.
    stale = dest_dir / "stale.json"
    stale.write_text("{}", encoding="utf-8")

    with pytest.raises(SeedError, match="zero domains"):
        run_seed(dataset_path, briefs_dir, dest_dir, check_only=False)
    assert stale.exists()


def test_run_seed_rejects_buckets_with_only_empty_lists(tmp_path: Path) -> None:
    """{'wordpress': []} also counts as zero domains."""
    dataset_path = tmp_path / "empty.json"
    dataset_path.write_text(
        json.dumps({"campaign": "test", "buckets": {"wordpress": [], "shopify": []}}),
        encoding="utf-8",
    )
    with pytest.raises(SeedError, match="zero domains"):
        run_seed(dataset_path, tmp_path / "briefs", tmp_path / "dest")


def test_load_dataset_rejects_non_object(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([]), encoding="utf-8")

    with pytest.raises(SeedError, match="root must be an object"):
        run_seed(bad, tmp_path, tmp_path / "dest")


def test_main_returns_zero_on_success(
    fixture_layout: tuple[Path, Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    dataset_path, briefs_dir, dest_dir = fixture_layout

    rc = main(
        [
            "--dataset",
            str(dataset_path),
            "--briefs-dir",
            str(briefs_dir),
            "--dest-dir",
            str(dest_dir),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "seeded 3 brief(s)" in out
    assert "campaign=dev-fixture" in out


def test_main_returns_one_on_missing(
    fixture_layout: tuple[Path, Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    dataset_path, briefs_dir, dest_dir = fixture_layout
    (briefs_dir / "alpha.dk.json").unlink()

    rc = main(
        [
            "--dataset",
            str(dataset_path),
            "--briefs-dir",
            str(briefs_dir),
            "--dest-dir",
            str(dest_dir),
        ]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "error:" in err
