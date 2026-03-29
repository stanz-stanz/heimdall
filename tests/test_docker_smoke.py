"""Docker smoke test — verify worker image assembly.

These tests verify that Go binaries, templates, and application code
are correctly installed in the Docker image and not overwritten by pip.

When run on the host (laptop/CI), they check paths relative to the
project root. When run inside the container, they check /app and
/opt paths directly.

Mark: @pytest.mark.docker — for container-only checks.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

# Detect if we're inside the Docker container
_IN_CONTAINER = Path("/app/src").is_dir() and Path("/opt/go-tools").is_dir()
_PROJECT_ROOT = Path("/app") if _IN_CONTAINER else Path(__file__).resolve().parent.parent


# --- Go binary checks ---


class TestGoBinaries:
    """Verify Go CLI tools are real binaries, not pip wrappers."""

    GO_TOOLS_DIR = Path("/opt/go-tools") if _IN_CONTAINER else _PROJECT_ROOT

    BINARIES = ["httpx", "webanalyze", "subfinder", "dnsx", "nuclei"]

    @pytest.mark.skipif(not _IN_CONTAINER, reason="Go binaries only in container")
    @pytest.mark.parametrize("binary", BINARIES)
    def test_binary_exists(self, binary):
        path = self.GO_TOOLS_DIR / binary
        assert path.is_file(), f"{binary} not found at {path}"

    @pytest.mark.skipif(not _IN_CONTAINER, reason="Go binaries only in container")
    @pytest.mark.parametrize("binary", BINARIES)
    def test_binary_not_pip_wrapper(self, binary):
        """Go binaries should be >1MB. Pip wrappers are ~200 bytes."""
        path = self.GO_TOOLS_DIR / binary
        if path.is_file():
            size = path.stat().st_size
            assert size > 1_000_000, (
                f"{binary} is only {size} bytes — likely a pip wrapper, not a Go binary"
            )

    @pytest.mark.skipif(not _IN_CONTAINER, reason="Go binaries only in container")
    def test_go_tools_first_in_path(self):
        path = os.environ.get("PATH", "")
        assert path.startswith("/opt/go-tools"), (
            f"PATH should start with /opt/go-tools but starts with: {path[:50]}"
        )


# --- Nuclei templates ---


class TestNucleiTemplates:
    """Verify Nuclei templates are baked into the image."""

    TEMPLATES_DIR = Path("/opt/nuclei-templates") if _IN_CONTAINER else None

    @pytest.mark.skipif(not _IN_CONTAINER, reason="Templates only in container")
    def test_templates_exist(self):
        assert self.TEMPLATES_DIR.is_dir()

    @pytest.mark.skipif(not _IN_CONTAINER, reason="Templates only in container")
    def test_minimum_template_count(self):
        count = len(list(self.TEMPLATES_DIR.rglob("*.yaml")))
        assert count >= 1000, f"Only {count} templates found, expected >= 1000"


# --- CMSeek ---


class TestCMSeek:
    """Verify CMSeek is cloned into the image."""

    CMSEEK_DIR = Path("/opt/cmseek") if _IN_CONTAINER else None

    @pytest.mark.skipif(not _IN_CONTAINER, reason="CMSeek only in container")
    def test_cmseek_exists(self):
        assert (self.CMSEEK_DIR / "cmseek.py").is_file()


# --- Application code ---


class TestApplicationCode:
    """Verify application code is correctly copied into the image."""

    def test_src_module_importable(self):
        """Core scan_job module should be importable."""
        from src.worker.scan_job import execute_scan_job
        assert callable(execute_scan_job)

    def test_tools_twin_exists(self):
        """tools/twin must be in the image for digital twin to work."""
        slug_map = _PROJECT_ROOT / "tools" / "twin" / "slug_map.json"
        assert slug_map.is_file(), f"slug_map.json not found at {slug_map}"

    def test_twin_module_importable(self):
        from tools.twin.templates import load_slug_map
        slug_map = load_slug_map()
        assert isinstance(slug_map, dict)
        assert len(slug_map) > 0

    def test_valdi_approvals_accessible(self):
        approvals = _PROJECT_ROOT / ".claude" / "agents" / "valdi" / "approvals.json"
        assert approvals.is_file(), f"approvals.json not found at {approvals}"

    def test_config_files_exist(self):
        config_dir = _PROJECT_ROOT / "config"
        for name in ["filters.json", "remediation_states.json", "synthetic_targets.json"]:
            assert (config_dir / name).is_file(), f"{name} missing from config/"


# --- Host-level checks (always run) ---


class TestDockerfileIntegrity:
    """Verify Dockerfile has pinned versions (not @latest)."""

    def test_no_latest_tags(self):
        dockerfile = _PROJECT_ROOT / "infra" / "docker" / "Dockerfile.worker"
        if not dockerfile.is_file():
            pytest.skip("Dockerfile not found (running inside container)")
        content = dockerfile.read_text()
        lines_with_latest = [
            line.strip() for line in content.splitlines()
            if "@latest" in line and line.strip().startswith("RUN")
        ]
        assert len(lines_with_latest) == 0, (
            f"Dockerfile has @latest tags (should be pinned):\n"
            + "\n".join(lines_with_latest)
        )

    def test_cmseek_commit_pinned(self):
        dockerfile = _PROJECT_ROOT / "infra" / "docker" / "Dockerfile.worker"
        if not dockerfile.is_file():
            pytest.skip("Dockerfile not found (running inside container)")
        content = dockerfile.read_text()
        assert "git checkout" in content, "CMSeek should be pinned to a specific commit"
