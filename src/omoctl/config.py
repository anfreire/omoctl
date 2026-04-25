from __future__ import annotations

import dataclasses
import re
import typing

import dacite
import yaml

from omoctl.output import die
from omoctl.paths import CONFIG_DIR, CONFIG_PATH, PROFILES_DIR
from omoctl.types import _UNSET


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

    @property
    def alias(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")[:50]


@dataclasses.dataclass
class Config:
    active_profile: str | None = None
    defaults: dict | None = None
    patches: list[Patch] | None = None
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

    def get_effective_overrides(self, profile: Profile) -> dict | None:
        if not self.defaults and not profile.overrides:
            return None
        result = dict(self.defaults) if self.defaults else {}
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


_DACITE_CONFIG = dacite.Config(check_types=False, strict=True)

_DEFAULT_YAML = """\
# active_profile: my-profile

defaults:
  disabled_hooks:
    - context-window-monitor

# patches:
#   - source: { provider: google }
#     target: { provider: proxy }

profiles:
  - name: Claude
    providers: [claude]

  - name: No Copilot
    providers: [claude, gemini, openai]
"""


def load_config() -> Config:
    if not CONFIG_PATH.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(_DEFAULT_YAML)
        die(
            f"No config found. A default has been created at {CONFIG_PATH}\n"
            f"  Edit it to define your profiles and re-run."
        )

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

    return config
