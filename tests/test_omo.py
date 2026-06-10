from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

import omoctl.omo as omo_mod
from omoctl.omo import fetch_omo_config

OMO_PAYLOAD = {"$schema": "s", "agents": {}, "categories": {}}


@pytest.fixture
def omo_paths(tmp_path: pathlib.Path, monkeypatch):
    active = tmp_path / "opencode/oh-my-openagent.jsonc"
    updated = tmp_path / "opencode/oh-my-openagent.json"
    backup = tmp_path / "omoctl/active-config.bak"
    active.parent.mkdir(parents=True)
    backup.parent.mkdir(parents=True)
    monkeypatch.setattr(omo_mod, "ACTIVE_CONFIG_PATH", active)
    monkeypatch.setattr(omo_mod, "UPDATED_CONFIG_PATH", updated)
    monkeypatch.setattr(omo_mod, "ACTIVE_BACKUP_PATH", backup)
    monkeypatch.setattr(omo_mod, "_find_runner", lambda: ("fake-runner",))
    monkeypatch.setattr(
        omo_mod, "get_available_providers", lambda: ("claude", "openai")
    )
    fetch_omo_config.cache_clear()
    yield {"active": active, "updated": updated, "backup": backup}
    fetch_omo_config.cache_clear()


def fake_run_success(updated: pathlib.Path):
    def _run(cmd, **kwargs):
        updated.write_text(json.dumps(OMO_PAYLOAD))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    return _run


class TestRecoverActiveBackup:
    def test_restores_when_active_missing(self, omo_paths):
        omo_paths["backup"].write_text("backup-content")
        omo_mod._recover_active_backup()
        assert omo_paths["active"].read_text() == "backup-content"
        assert not omo_paths["backup"].exists()

    def test_drops_stale_backup_when_active_present(self, omo_paths):
        omo_paths["active"].write_text("current")
        omo_paths["backup"].write_text("stale")
        omo_mod._recover_active_backup()
        assert omo_paths["active"].read_text() == "current"
        assert not omo_paths["backup"].exists()

    def test_noop_without_backup(self, omo_paths):
        omo_mod._recover_active_backup()
        assert not omo_paths["active"].exists()


class TestFetchOmoConfig:
    def test_returns_parsed_config_and_restores_active(self, omo_paths, monkeypatch):
        omo_paths["active"].write_text("active-content")
        monkeypatch.setattr(
            omo_mod.subprocess, "run", fake_run_success(omo_paths["updated"])
        )

        result = fetch_omo_config(("claude",), quiet=True)

        assert result == OMO_PAYLOAD
        assert omo_paths["active"].read_text() == "active-content"
        assert not omo_paths["backup"].exists()
        assert not omo_paths["updated"].exists()

    def test_failed_fetch_still_restores_active(self, omo_paths, monkeypatch):
        omo_paths["active"].write_text("active-content")

        def _run(cmd, **kwargs):
            raise subprocess.CalledProcessError(1, cmd, stderr="boom")

        monkeypatch.setattr(omo_mod.subprocess, "run", _run)

        with pytest.raises(SystemExit):
            fetch_omo_config(("claude",), quiet=True)

        assert omo_paths["active"].read_text() == "active-content"
        assert not omo_paths["backup"].exists()

    def test_recovers_from_previous_hard_kill(self, omo_paths, monkeypatch):
        # A previous run died after deleting the active config: only the
        # on-disk backup remains.
        omo_paths["backup"].write_text("lost-content")
        monkeypatch.setattr(
            omo_mod.subprocess, "run", fake_run_success(omo_paths["updated"])
        )

        fetch_omo_config(("claude",), quiet=True)

        assert omo_paths["active"].read_text() == "lost-content"
        assert not omo_paths["backup"].exists()

    def test_works_without_existing_active_config(self, omo_paths, monkeypatch):
        monkeypatch.setattr(
            omo_mod.subprocess, "run", fake_run_success(omo_paths["updated"])
        )
        result = fetch_omo_config(("claude",), quiet=True)
        assert result == OMO_PAYLOAD
        assert not omo_paths["active"].exists()

    def test_provider_flags_passed(self, omo_paths, monkeypatch):
        seen_cmds: list[list[str]] = []

        def _run(cmd, **kwargs):
            seen_cmds.append(list(cmd))
            omo_paths["updated"].write_text(json.dumps(OMO_PAYLOAD))
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(omo_mod.subprocess, "run", _run)
        fetch_omo_config(("claude",), quiet=True)

        assert seen_cmds, "install command was not run"
        cmd = seen_cmds[0]
        assert "--claude=yes" in cmd
        assert "--openai=no" in cmd
