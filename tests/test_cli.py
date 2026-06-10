"""Integration tests: run the real CLI in a sandboxed HOME.

These cover the active-profile display consistency guarantees: the state
file is the single source of truth, and every status view must agree.
"""

from __future__ import annotations

import json

from conftest import run_cli


class TestStatusConsistency:
    def test_all_views_agree_on_actual_state(self, sandbox):
        """Regression: a pinned active_profile used to override the actual
        state in `show`/`list` while -a/-n/-j reported the real one."""
        config_path = sandbox / ".config/omoctl/config.yaml"
        config_path.write_text("active_profile: Claude\n" + config_path.read_text())

        bare = run_cli(sandbox)
        assert "Default" in bare.stdout
        assert "Claude" not in bare.stdout

        assert run_cli(sandbox, "-a").stdout.strip() == "default"
        assert run_cli(sandbox, "-n").stdout.strip() == "Default"
        assert json.loads(run_cli(sandbox, "-j").stdout)["agents"]["a"]["model"] == (
            "openai/gpt-5.4"
        )

        listing = run_cli(sandbox, "list").stdout
        claude_line, default_line = (
            line
            for line in listing.splitlines()
            if "(claude)" in line or "(default)" in line
        )
        assert "●" in default_line
        assert "●" not in claude_line

    def test_nothing_active_is_consistent(self, sandbox):
        (sandbox / ".config/omoctl/active").unlink()

        bare = run_cli(sandbox)
        assert "No active profile" in bare.stdout

        for flag in ("-a", "-n"):
            result = run_cli(sandbox, flag)
            assert result.returncode == 1
            assert "No active profile" in result.stderr

    def test_stale_alias_reported_honestly(self, sandbox):
        (sandbox / ".config/omoctl/active").write_text("ghost")

        bare = run_cli(sandbox)
        assert "ghost" in bare.stdout
        assert "not defined in config.yaml" in bare.stdout

        assert run_cli(sandbox, "-a").stdout.strip() == "ghost"
        result = run_cli(sandbox, "-n")
        assert result.returncode == 1

    def test_flag_before_subcommand(self, sandbox):
        """Regression: `omoctl -a show` used to silently drop the flag."""
        assert run_cli(sandbox, "-a", "show").stdout.strip() == "default"
        assert run_cli(sandbox, "show", "-a").stdout.strip() == "default"

    def test_status_aliases(self, sandbox):
        for cmd in ("show", "current", "status"):
            assert run_cli(sandbox, cmd, "-a").stdout.strip() == "default"

    def test_json_missing_active_config_errors(self, sandbox):
        (sandbox / ".config/opencode/oh-my-openagent.jsonc").unlink()
        result = run_cli(sandbox, "-j")
        assert result.returncode == 1
        assert "No active config" in result.stderr


class TestUse:
    def test_use_switches_state_and_config(self, sandbox):
        result = run_cli(sandbox, "use", "claude")
        assert result.returncode == 0
        assert "Switched to profile" in result.stdout

        assert run_cli(sandbox, "-a").stdout.strip() == "claude"
        active = json.loads(
            (sandbox / ".config/opencode/oh-my-openagent.jsonc").read_text()
        )
        assert active["agents"]["a"]["model"] == "anthropic/claude-opus-4-7"

    def test_use_by_name_case_insensitive(self, sandbox):
        assert run_cli(sandbox, "use", "CLAUDE").returncode == 0
        assert run_cli(sandbox, "-a").stdout.strip() == "claude"

    def test_use_unknown_profile_errors(self, sandbox):
        result = run_cli(sandbox, "use", "nope")
        assert result.returncode == 1
        assert "not found" in result.stderr

    def test_use_unbuilt_profile_suggests_update(self, sandbox):
        (sandbox / ".config/omoctl/profiles/claude.json").unlink()
        result = run_cli(sandbox, "use", "claude")
        assert result.returncode == 1
        assert "omoctl update" in result.stderr


class TestRemove:
    def test_remove_deletes_stored_json_only(self, sandbox):
        result = run_cli(sandbox, "remove", "claude")
        assert result.returncode == 0
        assert not (sandbox / ".config/omoctl/profiles/claude.json").exists()
        assert "still in config.yaml" in result.stdout

    def test_remove_unknown_errors(self, sandbox):
        assert run_cli(sandbox, "remove", "nope").returncode == 1


class TestMisc:
    def test_version_flag_and_subcommand_agree(self, sandbox):
        from omoctl import __version__

        assert run_cli(sandbox, "version").stdout.strip() == f"omoctl {__version__}"
        assert run_cli(sandbox, "-v").stdout.strip() == f"omoctl {__version__}"

    def test_first_run_creates_config(self, tmp_path):
        result = run_cli(tmp_path)
        assert result.returncode == 1
        assert "created a default" in result.stderr
        assert (tmp_path / ".config/omoctl/config.yaml").exists()

    def test_malformed_filter_fails_fast_with_context(self, sandbox):
        config_path = sandbox / ".config/omoctl/config.yaml"
        config_path.write_text(
            config_path.read_text()
            + "    patches:\n"
            + "      - source: { provider: openai, model: { includes: [x] } }\n"
            + "        target: { model: y }\n"
        )
        result = run_cli(sandbox, "list")
        assert result.returncode == 1
        assert "unknown key" in result.stderr
        assert "Default" in result.stderr  # context names the profile

    def test_unknown_command_errors(self, sandbox):
        result = run_cli(sandbox, "bogus")
        assert result.returncode == 2
        assert "invalid choice" in result.stderr
