from __future__ import annotations

import pathlib

import pytest

import omoctl.config as config_mod
from omoctl.config import (
    Config,
    Patch,
    PatchSource,
    PatchTarget,
    Profile,
    load_config,
    merge_dicts,
)


@pytest.fixture
def config_home(tmp_path: pathlib.Path, monkeypatch) -> pathlib.Path:
    config_dir = tmp_path / "omoctl"
    monkeypatch.setattr(config_mod, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_mod, "CONFIG_PATH", config_dir / "config.yaml")
    monkeypatch.setattr(config_mod, "PROFILES_DIR", config_dir / "profiles")
    return config_dir


def write_config(config_dir: pathlib.Path, text: str) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(text)


class TestLoadConfig:
    def test_first_run_creates_default_and_exits(self, config_home, capsys):
        with pytest.raises(SystemExit) as exc:
            load_config()
        assert exc.value.code == 1
        assert (config_home / "config.yaml").exists()
        assert "created a default" in capsys.readouterr().err

    def test_created_default_is_loadable(self, config_home):
        with pytest.raises(SystemExit):
            load_config()
        config = load_config()
        assert [p.name for p in config.profiles] == ["Claude", "Default"]

    def test_valid_config(self, config_home):
        write_config(
            config_home,
            "active_profile: Claude\n"
            "profiles:\n"
            "  - name: Claude\n"
            "    providers: [claude]\n",
        )
        config = load_config()
        assert config.active_profile == "Claude"
        assert config.profiles[0].alias == "claude"

    def test_invalid_yaml_dies(self, config_home, capsys):
        write_config(config_home, "profiles: [\n")
        with pytest.raises(SystemExit):
            load_config()
        assert "invalid YAML" in capsys.readouterr().err

    def test_unknown_key_dies(self, config_home, capsys):
        write_config(
            config_home,
            "profiles:\n  - name: Claude\n    provders: [claude]\n",  # typo
        )
        with pytest.raises(SystemExit):
            load_config()
        assert "invalid structure" in capsys.readouterr().err

    def test_wrong_type_dies(self, config_home, capsys):
        write_config(
            config_home,
            "profiles:\n  - name: Claude\n    providers: claude\n",  # string, not list
        )
        with pytest.raises(SystemExit):
            load_config()
        assert "invalid structure" in capsys.readouterr().err

    def test_alias_collision_dies(self, config_home, capsys):
        write_config(
            config_home,
            "profiles:\n"
            "  - name: My Profile\n"
            "    providers: [claude]\n"
            "  - name: my-profile\n"
            "    providers: [claude]\n",
        )
        with pytest.raises(SystemExit):
            load_config()
        assert "collides" in capsys.readouterr().err

    def test_malformed_model_spec_dies_at_load(self, config_home, capsys):
        """Regression: malformed filters used to crash `update` with a traceback."""
        write_config(
            config_home,
            "profiles:\n"
            "  - name: Claude\n"
            "    providers: [claude]\n"
            "    patches:\n"
            "      - source: { provider: openai, model: { includes: [opus] } }\n"
            "        target: { model: gpt-5.4 }\n",
        )
        with pytest.raises(SystemExit):
            load_config()
        err = capsys.readouterr().err
        assert "profile 'Claude' patch [0] source" in err
        assert "unknown key" in err

    def test_malformed_global_remove_fallbacks_dies_at_load(self, config_home, capsys):
        write_config(
            config_home,
            "remove_fallbacks:\n"
            "  - provider: openai\n"
            "    model: 5\n"
            "profiles:\n"
            "  - name: Claude\n"
            "    providers: [claude]\n",
        )
        with pytest.raises(SystemExit):
            load_config()
        assert "global remove_fallbacks [0]" in capsys.readouterr().err


class TestConfigHelpers:
    def make_config(self) -> Config:
        profile = Profile(
            name="Test",
            providers=["claude"],
            patches=[
                Patch(source=PatchSource(agent="p"), target=PatchTarget(model="x"))
            ],
            remove_fallbacks=[PatchSource(provider="p")],
            overrides={"a": {"b": 1}, "keep": "profile"},
        )
        return Config(
            patches=[
                Patch(source=PatchSource(agent="g"), target=PatchTarget(model="y"))
            ],
            remove_fallbacks=[PatchSource(provider="g")],
            overrides={"a": {"c": 2}, "keep": "global"},
            profiles=[profile],
        )

    def test_find_profile_by_name_case_insensitive(self):
        config = self.make_config()
        assert config.find_profile("test") is config.profiles[0]
        assert config.find_profile("TEST") is config.profiles[0]
        assert config.find_profile("nope") is None

    def test_find_profile_by_alias(self):
        profile = Profile(name="No Copilot", providers=["claude"])
        config = Config(profiles=[profile])
        assert config.find_profile("no-copilot") is profile

    def test_effective_patches_profile_first(self):
        config = self.make_config()
        patches = config.get_effective_patches(config.profiles[0])
        assert [p.source.agent for p in patches] == ["p", "g"]

    def test_effective_remove_fallbacks_profile_first(self):
        config = self.make_config()
        sources = config.get_effective_remove_fallbacks(config.profiles[0])
        assert [s.provider for s in sources] == ["p", "g"]

    def test_effective_overrides_deep_merge_profile_wins(self):
        config = self.make_config()
        overrides = config.get_effective_overrides(config.profiles[0])
        assert overrides == {"a": {"b": 1, "c": 2}, "keep": "profile"}

    def test_merge_dicts_nested(self):
        assert merge_dicts({"a": {"x": 1}, "b": 1}, {"a": {"y": 2}, "b": 2}) == {
            "a": {"x": 1, "y": 2},
            "b": 2,
        }

    def test_alias_normalization(self):
        assert Profile(name="No Copilot!", providers=[]).alias == "no-copilot"
        assert Profile(name="A" * 80, providers=[]).alias == "a" * 50
