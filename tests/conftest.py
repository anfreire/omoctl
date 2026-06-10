from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent
SRC_DIR = REPO_ROOT / "src"

MINIMAL_OMO = {
    "$schema": "schema",
    "agents": {"a": {"model": "anthropic/claude-opus-4-7"}},
    "categories": {},
}


def run_cli(home: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the real CLI in a sandboxed HOME."""
    env = {**os.environ, "HOME": str(home), "PYTHONPATH": str(SRC_DIR)}
    return subprocess.run(
        [sys.executable, "-m", "omoctl", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


@pytest.fixture
def sandbox(tmp_path: pathlib.Path) -> pathlib.Path:
    """A fake HOME with two profiles: Claude (built) and Default (built+active)."""
    omoctl_dir = tmp_path / ".config/omoctl"
    profiles_dir = omoctl_dir / "profiles"
    opencode_dir = tmp_path / ".config/opencode"
    profiles_dir.mkdir(parents=True)
    opencode_dir.mkdir(parents=True)

    (omoctl_dir / "config.yaml").write_text(
        "profiles:\n"
        "  - name: Claude\n"
        "    providers: [claude]\n"
        "  - name: Default\n"
        "    providers: [claude, openai]\n"
    )

    claude_cfg = dict(MINIMAL_OMO)
    default_cfg = {
        "$schema": "schema",
        "agents": {"a": {"model": "openai/gpt-5.4"}},
        "categories": {},
    }
    (profiles_dir / "claude.json").write_text(json.dumps(claude_cfg))
    (profiles_dir / "default.json").write_text(json.dumps(default_cfg))

    (omoctl_dir / "active").write_text("default")
    (opencode_dir / "oh-my-openagent.jsonc").write_text(json.dumps(default_cfg))

    return tmp_path
