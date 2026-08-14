"""`~/.config/omoctl/config.yaml` — the only file you edit."""

from __future__ import annotations

import re
import typing

import pydantic
import yaml

from omoctl.models import Filter, parse_filter
from omoctl.paths import CONFIG_PATH, PROFILES_DIR
from omoctl.render import console, die

Json = dict[str, typing.Any]

# Whatever `oh-my-openagent install` accepts. omoctl never inspects the names
# or the values; `None` means a flag that takes no value.
Install = dict[str, str | bool | int | float | None]

_STRICT = pydantic.ConfigDict(extra="forbid")


def deep_merge(base: Json, over: Json) -> Json:
    result = dict(base)
    for key, value in over.items():
        current = result.get(key)
        result[key] = (
            deep_merge(current, value)
            if isinstance(current, dict) and isinstance(value, dict)
            else value
        )
    return result


def _glob(pattern: str) -> str:
    """Compile a `where` into an fnmatch pattern.

    Paths carry OMO's harness block verbatim (`[opencode].agents.oracle.model`),
    and fnmatch would read those brackets as a character class — so a path
    pasted straight out of a diff would match nothing. Escape them to literals,
    which leaves `*` and `?` as the only glob syntax; a pattern using neither is
    a plain word, meant as "somewhere in the path".
    """
    literal = pattern.replace("[", "[[]")
    return literal if any(c in pattern for c in "*?") else f"*{literal}*"


class Match(pydantic.BaseModel):
    """Which model references a patch or drop applies to."""

    model_config = _STRICT

    where: str | None = None
    provider: str | None = None
    model: typing.Any = None

    spec: Filter | str | None = pydantic.Field(default=None, exclude=True, init=False)
    glob: str | None = pydantic.Field(default=None, exclude=True, init=False)

    @pydantic.model_validator(mode="after")
    def _compile(self) -> Match:
        if self.where is None and self.provider is None and self.model is None:
            raise ValueError("needs at least one of `where`, `provider`, or `model`")
        self.spec = parse_filter(self.model)
        self.glob = _glob(self.where) if self.where else None
        return self

    @property
    def label(self) -> str:
        pairs = {"where": self.where, "provider": self.provider, "model": self.model}
        return " ".join(f"{k}={v}" for k, v in pairs.items() if v is not None)


class Patch(pydantic.BaseModel):
    model_config = _STRICT

    match: Match
    set: Json

    @pydantic.field_validator("set")
    @classmethod
    def _assignable(cls, value: Json) -> Json:
        if not value:
            raise ValueError("must assign at least one key")
        if "model" in value and value["model"] is None:
            raise ValueError("`model` cannot be null; an entry without a model is not a model")
        lists = sorted(k for k in value if k.endswith("models"))
        if lists:
            # Replacing a whole list is a structural edit, not a rewrite of the
            # references inside it. `overrides` does that, and keeping it out of
            # `set` means a patch can never invalidate another patch's target.
            raise ValueError(
                f"cannot assign {', '.join(lists)}; use `overrides` to replace a model list"
            )
        parse_filter(value.get("model"))  # fail here rather than mid-update
        return value


class Profile(pydantic.BaseModel):
    model_config = _STRICT

    name: str = pydantic.Field(min_length=1)
    install: Install = pydantic.Field(default_factory=dict)
    patches: list[Patch] = pydantic.Field(default_factory=list)
    drop: list[Match] = pydantic.Field(default_factory=list)
    overrides: Json = pydantic.Field(default_factory=dict)

    @property
    def alias(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")[:50]


class Config(pydantic.BaseModel):
    model_config = _STRICT

    activate: str | None = None
    install: Install = pydantic.Field(default_factory=dict)
    patches: list[Patch] = pydantic.Field(default_factory=list)
    drop: list[Match] = pydantic.Field(default_factory=list)
    overrides: Json = pydantic.Field(default_factory=dict)
    profiles: list[Profile] = pydantic.Field(min_length=1)

    @pydantic.model_validator(mode="after")
    def _unique_aliases(self) -> Config:
        seen: dict[str, str] = {}
        for profile in self.profiles:
            if not profile.alias:
                raise ValueError(
                    f"profile {profile.name!r} has no letters or digits to form an alias"
                )
            if profile.alias in seen:
                raise ValueError(
                    f"profiles {seen[profile.alias]!r} and {profile.name!r} both reduce to "
                    f"alias {profile.alias!r}; rename one"
                )
            seen[profile.alias] = profile.name
        if self.activate and self.find(self.activate) is None:
            raise ValueError(f"`activate` names {self.activate!r}, which is not a defined profile")
        return self

    def find(self, name_or_alias: str) -> Profile | None:
        key = name_or_alias.lower()
        return next((p for p in self.profiles if p.name.lower() == key or p.alias == key), None)

    # Profile settings win over global ones: install flags and overrides are
    # merged over the global values, and profile patches are tried first.
    def install_for(self, profile: Profile) -> Install:
        return {**self.install, **profile.install}

    def patches_for(self, profile: Profile) -> list[Patch]:
        return [*profile.patches, *self.patches]

    def drops_for(self, profile: Profile) -> list[Match]:
        return [*profile.drop, *self.drop]

    def overrides_for(self, profile: Profile) -> Json:
        return deep_merge(self.overrides, profile.overrides)


DEFAULT_YAML = """\
# omoctl config. Run `omoctl providers` to see every flag `install:` accepts,
# straight from oh-my-openagent itself.

# Install flags every profile inherits. Profiles merge their own on top.
install:
  claude: no
  gemini: no
  copilot: no

profiles:
  - name: Claude
    install: { claude: yes }

  - name: Everything
    install: { claude: yes, openai: yes, gemini: yes }

# Switch to this profile after every `omoctl update`.
# activate: Claude

# Rewrite models. `match` selects references, `set` assigns keys onto them
# (a null value deletes the key). Profile patches are tried before these.
# patches:
#   - match: { provider: anthropic, model: [sonnet] }
#     set:   { model: claude-opus-5 }
#   - match: { where: oracle }
#     set:   { provider: opencode-go, model: glm-5.2, variant: null }

# Drop entries from fallback_models / models lists. Same `match` syntax.
# drop:
#   - { provider: openai, model: gpt-5-nano }

# Deep-merged into the final ~/.omo/omo.jsonc.
# overrides:
#   "[opencode]":
#     disabled_hooks: [context-window-monitor]
"""


def _where(error: pydantic.ValidationError) -> typing.Iterator[str]:
    for item in error.errors():
        loc = ".".join(str(part) for part in item["loc"])
        yield f"{loc}: {item['msg']}" if loc else item["msg"]


def load() -> Config:
    if not CONFIG_PATH.exists():
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(DEFAULT_YAML)
        console.print(f"Created a starter config at [bold]{CONFIG_PATH}[/]. Edit it, then re-run.")
        raise SystemExit(0)

    try:
        raw = yaml.safe_load(CONFIG_PATH.read_text())
    except yaml.YAMLError as exc:
        die(f"{CONFIG_PATH} is not valid YAML:\n  {exc}")

    try:
        return Config.model_validate(raw or {})
    except pydantic.ValidationError as exc:
        die("\n  ".join([f"{CONFIG_PATH}:", *_where(exc)]))


__all__ = ["Config", "Install", "Json", "Match", "Patch", "Profile", "deep_merge", "load"]
