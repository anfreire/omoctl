from __future__ import annotations

import dataclasses
import re
import sys
import typing

import dacite
import yaml

from omoctl.output import BOLD, GREEN, RESET, die
from omoctl.paths import CONFIG_DIR, CONFIG_PATH, PROFILES_DIR
from omoctl.types import _UNSET, parse_model_spec


@dataclasses.dataclass
class PatchSource:
    provider: str | None = None
    model: typing.Any = None
    agent: str | None = None
    category: str | None = None


@dataclasses.dataclass
class PatchTarget:
    provider: str | None = None
    model: typing.Any = None
    variant: typing.Any = dataclasses.field(default=_UNSET)


@dataclasses.dataclass
class Patch:
    source: PatchSource = dataclasses.field(default_factory=PatchSource)
    target: PatchTarget = dataclasses.field(default_factory=PatchTarget)


@dataclasses.dataclass
class Profile:
    name: str = ""
    providers: list[str] = dataclasses.field(default_factory=list)
    patches: list[Patch] | None = None
    overrides: dict | None = None
    remove_fallbacks: list[PatchSource] | None = None

    @property
    def alias(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")[:50]


@dataclasses.dataclass
class Config:
    active_profile: str | None = None
    overrides: dict | None = None
    patches: list[Patch] | None = None
    remove_fallbacks: list[PatchSource] | None = None
    profiles: list[Profile] = dataclasses.field(default_factory=list)

    def find_profile(self, name_or_alias: str) -> Profile | None:
        key = name_or_alias.lower()
        for profile in self.profiles:
            if profile.name.lower() == key or profile.alias == key:
                return profile
        return None

    def get_active_profile(self) -> Profile | None:
        if self.active_profile is None:
            return None
        return self.find_profile(self.active_profile)

    def get_effective_patches(self, profile: Profile) -> list[Patch]:
        result: list[Patch] = []
        if profile.patches:
            result.extend(profile.patches)
        if self.patches:
            result.extend(self.patches)
        return result

    def get_effective_remove_fallbacks(self, profile: Profile) -> list[PatchSource]:
        result: list[PatchSource] = []
        if profile.remove_fallbacks:
            result.extend(profile.remove_fallbacks)
        if self.remove_fallbacks:
            result.extend(self.remove_fallbacks)
        return result

    def get_effective_overrides(self, profile: Profile) -> dict | None:
        if not self.overrides and not profile.overrides:
            return None
        result = dict(self.overrides) if self.overrides else {}
        if profile.overrides:
            result = merge_dicts(result, profile.overrides)
        return result or None


def merge_dicts(
    base: dict[str, typing.Any], override: dict[str, typing.Any]
) -> dict[str, typing.Any]:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


_DACITE_CONFIG = dacite.Config(check_types=True, strict=True)

_DEFAULT_YAML = """\
# omoctl default config. This is verbose on purpose so you can see every
# option that exists. Uncomment, edit, or delete what you don't need.
# Run `omoctl check` to validate the config against live data.

# Auto-activate this profile after `omoctl update`. Optional.
# active_profile: Claude

# OMO config overrides applied to all profiles (deep-merged into the
# final OMO config). See the oh-my-openagent schema for valid keys.
overrides:
  disabled_hooks:
    - context-window-monitor

# Global patches applied to all profiles. Profile patches take priority.
# A patch rewrites a model when its source matches; see the README for
# the full matcher syntax (provider / model / agent / category).
# patches:
#   - source: { provider: anthropic, model: claude-sonnet-4-6 }
#     target: { model: claude-opus-4-6 }
#   - { source: { provider: anthropic, model: [opus] }, target: { model: claude-opus-4-6 } }
#   - source:
#       provider: anthropic
#       model:
#         include: [claude]
#         exclude: [haiku]
#     target: { model: claude-sonnet-4-6 }
#   - source: { agent: sisyphus }
#     target: { provider: openai, model: gpt-5.4 }
#   - source: { category: ultrabrain }
#     target: { provider: openai, model: gpt-5.4, variant: xhigh }
#   - source: { agent: sisyphus, model: claude-opus-4-7 }
#     target: { variant: null }

# Drop these models from any agent's or category's fallback_models lists.
# Match is done against the ORIGINAL OMO model (not the post-patch model).
# Each entry uses the same source fields as patches: provider, model,
# agent, category. At least one of provider / agent / category must be set.
# remove_fallbacks:
#   - provider: openai
#     model: gpt-5.5-fast
#   - { agent: sisyphus, provider: openai }

profiles:
  - name: Claude
    providers: [claude]
    # Per-profile overrides are deep-merged on top of global overrides.
    # overrides:
    #   claude_code:
    #     agents: false
    #     commands: false
    #     hooks: false
    #     mcp: false
    #     plugins: false
    #     skills: false


  - name: Default
    providers: [claude, openai, gemini]
    # Per-profile patches take priority over global patches.
    # patches:
    #   - source: { provider: openai, model: gpt-5.4-mini-fast }
    #     target: { model: gpt-5.4-mini }
    # Per-profile remove_fallbacks add to the global list.
    # remove_fallbacks:
    #   - provider: openai
    #     model: gpt-5.5
"""


def _check_model_specs(config: Config) -> None:
    """Die with context if any patch/remove_fallbacks model spec is malformed.

    Running this at load time means every command fails fast with a clear
    message instead of crashing mid-update.
    """
    specs: list[tuple[str, typing.Any]] = []

    def collect(
        owner: str,
        patches: list[Patch] | None,
        remove_fallbacks: list[PatchSource] | None,
    ) -> None:
        for i, patch in enumerate(patches or []):
            specs.append((f"{owner}patch [{i}] source", patch.source.model))
            specs.append((f"{owner}patch [{i}] target", patch.target.model))
        for i, source in enumerate(remove_fallbacks or []):
            specs.append((f"{owner}remove_fallbacks [{i}]", source.model))

    collect("global ", config.patches, config.remove_fallbacks)
    for profile in config.profiles:
        collect(f"profile {profile.name!r} ", profile.patches, profile.remove_fallbacks)

    for ctx, raw in specs:
        try:
            parse_model_spec(raw)
        except ValueError as e:
            die(f"Config at {CONFIG_PATH}:\n  {ctx}: {e}")


def load_config() -> Config:
    if not CONFIG_PATH.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(_DEFAULT_YAML)
        print(
            f"{GREEN}No config found — created a default at "
            f"{BOLD}{CONFIG_PATH}{RESET}\n"
            f"  Edit it to define your profiles, then re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        with CONFIG_PATH.open() as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        die(f"Config at {CONFIG_PATH} has invalid YAML:\n  {e}")

    if not data or not data.get("profiles"):
        die(f"No profiles defined in {CONFIG_PATH}. Add at least one profile.")

    try:
        config = dacite.from_dict(Config, data, config=_DACITE_CONFIG)
    except dacite.DaciteError as e:
        die(f"Config at {CONFIG_PATH} has invalid structure:\n  {e}")

    seen_aliases: dict[str, str] = {}
    for profile in config.profiles:
        if not profile.name:
            die("Each profile must have a 'name' field.")
        if not profile.providers:
            die(f"Profile {profile.name!r} must have a 'providers' field.")
        if profile.alias in seen_aliases:
            die(
                f"Profile {profile.name!r} produces alias {profile.alias!r} "
                f"which collides with profile {seen_aliases[profile.alias]!r}.\n"
                f"  Rename one of them so they produce distinct aliases."
            )
        seen_aliases[profile.alias] = profile.name

    _check_model_specs(config)

    return config
